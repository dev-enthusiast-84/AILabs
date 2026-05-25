"""
Zero-cost notification channels: SMTP email (stdlib smtplib) + ntfy.sh push.

Each public function sends a message whose subject and body are tailored to the
specific event that triggered it — admins receive enough context to understand
*what happened*, *why it matters*, and *what to do next*.

OWASP A09 — SMTP password is never logged. ntfy topic is treated as a shared secret.
"""
import asyncio
import smtplib
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText

import structlog

log = structlog.get_logger()

NOTIFICATION_DEDUP_SECONDS = 86400  # 24 h
_last_notified_at: float = 0.0


# ── Shared channel dispatcher ─────────────────────────────────────────────────

async def _notify_all_channels(
    subject: str,
    body: str,
    priority: str = "default",
    tags: str = "",
) -> dict:
    """Send subject/body to every configured channel.

    Returns {email_sent, ntfy_sent, errors}. Never raises — all channel errors
    are captured in the errors list so a single failing channel cannot block
    delivery to others.
    """
    from app.config import get_settings
    from app.runtime.settings_store import (
        get_effective_notification_email,
        get_effective_notification_ntfy_topic,
    )
    cfg = get_settings()
    email_sent = False
    ntfy_sent = False
    errors: list[str] = []

    effective_email = get_effective_notification_email()
    effective_ntfy_topic = get_effective_notification_ntfy_topic()

    if cfg.notification_smtp_host and effective_email:
        try:
            await asyncio.to_thread(
                _send_smtp,
                cfg.notification_smtp_host,
                cfg.notification_smtp_port,
                cfg.notification_smtp_user,
                cfg.notification_smtp_password,
                effective_email,
                subject,
                body,
            )
            email_sent = True
            log.info("notification_email_sent", to=effective_email, subject=subject)
        except Exception as exc:
            errors.append(f"email: {type(exc).__name__}: {exc}")
            log.error("notification_email_failed", error_type=type(exc).__name__)

    if effective_ntfy_topic:
        try:
            import httpx
            # ntfy.sh supports UTF-8 header values; encode as bytes so httpx
            # does not try to force-encode emoji/non-ASCII as latin-1.
            headers: dict[str, bytes | str] = {
                "Title": subject.encode("utf-8"),
                "Priority": priority,
            }
            if tags:
                headers["Tags"] = tags
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://ntfy.sh/{effective_ntfy_topic}",
                    headers=headers,
                    content=body.encode("utf-8"),
                )
            ntfy_sent = True
            log.info("notification_ntfy_sent", subject=subject)
        except Exception as exc:
            errors.append(f"ntfy: {type(exc).__name__}: {exc}")
            log.error("notification_ntfy_failed", error_type=type(exc).__name__)

    return {"email_sent": email_sent, "ntfy_sent": ntfy_sent, "errors": errors}


# ── Use-case notifications ────────────────────────────────────────────────────

async def send_limit_warning(doc_count: int, doc_limit: int) -> None:
    """Near-limit warning when admin doc count reaches ≥ 80% of the configured maximum.

    Deduplicates within NOTIFICATION_DEDUP_SECONDS to prevent alert storms on
    rapid consecutive uploads. Errors are caught and logged — never raised.
    """
    global _last_notified_at
    from app.config import get_settings
    cfg = get_settings()
    if not cfg.notification_enabled:
        return
    now = time.time()
    if now - _last_notified_at < NOTIFICATION_DEDUP_SECONDS:
        log.info("notification_dedup_skipped")
        return
    _last_notified_at = now

    pct = int(doc_count / doc_limit * 100)
    subject = f"⚠️ Document limit: {doc_count}/{doc_limit} indexed ({pct}%)"
    body = (
        f"Your Agentic RAG application is approaching the admin document limit.\n\n"
        f"Current status : {doc_count} of {doc_limit} documents indexed ({pct}%)\n\n"
        f"Recommended actions:\n"
        f"  • Open the admin panel and click “Clean up” to remove\n"
        f"    documents older than your retention window.\n"
        f"  • Review the retention cadence in Settings → Document Cleanup.\n"
        f"  • If the limit is too low, increase ADMIN_MAX_INDEXED_DOCUMENTS\n"
        f"    in your environment configuration.\n\n"
        f"Once the limit is reached ({doc_limit} documents) new uploads will be\n"
        f"rejected until space is freed.\n\n"
        f"Sent at: {_utc_now()}"
    )
    await _notify_all_channels(subject, body, priority="high", tags="warning")


async def send_cleanup_notification(result) -> None:  # result: CleanupResult
    """Post-cleanup summary sent after every admin sweep (manual or scheduled).

    Tells the admin what ran, how many documents were removed, which files were
    deleted, the retention window that was applied, and any partial errors —
    enough context to audit or troubleshoot without opening the app.

    Errors are caught and logged — never raised to callers.
    """
    from app.config import get_settings
    cfg = get_settings()
    if not cfg.notification_enabled:
        return

    try:
        deleted = result.deleted_count
        eligible = result.eligible_count
        force = result.force_mode
        retention_hours = result.retention_hours
        trigger = result.trigger          # "manual" | "session_start"
        errors = result.errors or []
        deleted_sources = result.deleted_sources or []
        ran_at = result.ran_at

        # ── Subject ───────────────────────────────────────────────────────────
        if force:
            subject = f"\U0001f9f9 Force cleanup — all {deleted} admin document(s) removed"
        elif deleted == 0:
            subject = f"\U0001f9f9 Cleanup ran — no expired documents found"
        else:
            subject = f"\U0001f9f9 Cleanup complete — {deleted} document(s) removed"
        if errors:
            subject += " (with errors)"

        # ── Retention window line ─────────────────────────────────────────────
        if force:
            retention_line = "Mode              : Force (all admin documents)"
        elif retention_hours is not None:
            if retention_hours < 24:
                rwindow = f"{retention_hours}h"
            elif retention_hours % 720 == 0:
                rwindow = f"{retention_hours // 720} month(s)"
            elif retention_hours % 168 == 0:
                rwindow = f"{retention_hours // 168} week(s)"
            else:
                rwindow = f"{retention_hours // 24}d"
            retention_line = f"Retention window  : {rwindow} (documents older than this were eligible)"
        else:
            retention_line = "Retention window  : N/A"

        # ── Deleted files section ─────────────────────────────────────────────
        if deleted_sources:
            files_section = "Deleted files:\n" + "\n".join(
                f"  • {src}" for src in deleted_sources[:20]
            )
            if len(deleted_sources) > 20:
                files_section += f"\n  … and {len(deleted_sources) - 20} more"
        else:
            files_section = "No files were deleted."

        # ── Error section ─────────────────────────────────────────────────────
        errors_section = ""
        if errors:
            errors_section = (
                "\nPartial errors (cleanup may be incomplete):\n"
                + "\n".join(f"  • {e}" for e in errors[:10])
            )

        body = (
            f"Admin document cleanup has completed.\n\n"
            f"Summary\n"
            f"-------\n"
            f"Trigger           : {trigger.capitalize()}\n"
            f"Documents removed : {deleted}\n"
            f"Documents checked : {eligible}\n"
            f"{retention_line}\n"
            f"Completed at      : {ran_at}\n\n"
            f"{files_section}"
            f"{errors_section}\n\n"
            f"Sent at: {_utc_now()}"
        )

        priority = "high" if errors else "default"
        tags = "warning" if errors else "white_check_mark"
        await _notify_all_channels(subject, body, priority=priority, tags=tags)
    except Exception as exc:
        log.error("cleanup_notification_failed", error_type=type(exc).__name__)


async def send_test_notification() -> dict:
    """Bypass dedup and verify all configured channels are reachable.

    Returns {email_sent, ntfy_sent, errors}. Reports which channels are
    active so the admin can confirm the configuration is complete.
    """
    from app.config import get_settings
    from app.runtime.settings_store import (
        get_effective_notification_email,
        get_effective_notification_ntfy_topic,
    )
    cfg = get_settings()
    effective_email = get_effective_notification_email()
    effective_ntfy_topic = get_effective_notification_ntfy_topic()

    email_channel = (
        f"Email  ✓  ({effective_email})"
        if cfg.notification_smtp_host and effective_email
        else "Email  ✗  (not configured — set NOTIFICATION_SMTP_HOST + NOTIFICATION_EMAIL)"
    )
    ntfy_channel = (
        f"ntfy.sh  ✓  (topic: {effective_ntfy_topic})"
        if effective_ntfy_topic
        else "ntfy.sh  ✗  (not configured — set NOTIFICATION_NTFY_TOPIC)"
    )

    subject = "✅ Test notification — Agentic RAG"
    body = (
        f"This is a test notification from your Agentic RAG system.\n\n"
        f"If you received this message, your notification setup is working correctly.\n\n"
        f"Configured channels:\n"
        f"  {email_channel}\n"
        f"  {ntfy_channel}\n\n"
        f"Sent at: {_utc_now()}"
    )

    return await _notify_all_channels(subject, body, priority="default", tags="bell")


# ── SMTP helper ───────────────────────────────────────────────────────────────

def _send_smtp(host: str, port: int, user: str, password: str, to_email: str, subject: str, body: str) -> None:
    """Send an email via SMTP with STARTTLS. Password is never logged (OWASP A09)."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user or "noreply@ragapp"
    msg["To"] = to_email
    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)  # password never logged
        smtp.sendmail(msg["From"], [to_email], msg.as_string())


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
