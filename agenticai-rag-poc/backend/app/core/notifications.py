"""
Zero-cost notification channels: SMTP email (stdlib smtplib) + ntfy.sh push.

OWASP A09 — SMTP password is never logged. ntfy topic is treated as shared secret.
"""
import asyncio
import smtplib
import time
from email.mime.text import MIMEText

import structlog

log = structlog.get_logger()

NOTIFICATION_DEDUP_SECONDS = 86400  # 24 h
_last_notified_at: float = 0.0


async def send_limit_warning(doc_count: int, doc_limit: int) -> None:
    """Send near-limit warning via all configured notification channels.

    Deduplicates within NOTIFICATION_DEDUP_SECONDS to avoid notification storms.
    Errors are caught and logged — never raised to callers.
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
    subject = f"Document limit warning: {doc_count}/{doc_limit} documents indexed"
    body = (
        f"Your RAG application has {doc_count} of {doc_limit} documents indexed "
        f"({doc_count / doc_limit:.0%}). Consider running cleanup."
    )
    if cfg.notification_smtp_host and cfg.notification_email:
        try:
            await asyncio.to_thread(
                _send_smtp,
                cfg.notification_smtp_host,
                cfg.notification_smtp_port,
                cfg.notification_smtp_user,
                cfg.notification_smtp_password,
                cfg.notification_email,
                subject,
                body,
            )
            log.info("notification_email_sent", to=cfg.notification_email)
        except Exception as exc:
            log.error("notification_email_failed", error_type=type(exc).__name__)

    if cfg.notification_ntfy_topic:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://ntfy.sh/{cfg.notification_ntfy_topic}",
                    headers={"Title": subject, "Priority": "high"},
                    content=body,
                )
            log.info("notification_ntfy_sent")
        except Exception as exc:
            log.error("notification_ntfy_failed", error_type=type(exc).__name__)


async def send_test_notification() -> dict:
    """Bypass dedup and test both channels. Returns email_sent, ntfy_sent, errors."""
    from app.config import get_settings
    cfg = get_settings()
    email_sent = False
    ntfy_sent = False
    errors: list[str] = []

    if cfg.notification_smtp_host and cfg.notification_email:
        try:
            await asyncio.to_thread(
                _send_smtp,
                cfg.notification_smtp_host,
                cfg.notification_smtp_port,
                cfg.notification_smtp_user,
                cfg.notification_smtp_password,
                cfg.notification_email,
                "Test notification from RAG app",
                "This is a test notification.",
            )
            email_sent = True
        except Exception as exc:
            errors.append(f"email: {type(exc).__name__}: {exc}")

    if cfg.notification_ntfy_topic:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://ntfy.sh/{cfg.notification_ntfy_topic}",
                    headers={"Title": "Test notification", "Priority": "default"},
                    content="This is a test notification from your RAG app.",
                )
            ntfy_sent = True
        except Exception as exc:
            errors.append(f"ntfy: {type(exc).__name__}: {exc}")

    return {"email_sent": email_sent, "ntfy_sent": ntfy_sent, "errors": errors}


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
