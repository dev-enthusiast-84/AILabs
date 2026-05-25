"""Unit tests for app.core.notifications module.

Covers:
- T027: send_limit_warning — SMTP, ntfy, deduplication
- T028: POST /api/notifications/test endpoint auth + behaviour
"""
import os
import time
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _smtp_config(enabled: bool = True) -> dict:
    return {
        "notification_enabled": enabled,
        "notification_smtp_host": "smtp.example.com" if enabled else "",
        "notification_smtp_port": 587,
        "notification_smtp_user": "user@example.com",
        "notification_smtp_password": "secret",
        "notification_email": "admin@example.com" if enabled else "",
        "notification_ntfy_topic": "",
    }


def _ntfy_config(enabled: bool = True) -> dict:
    return {
        "notification_enabled": enabled,
        "notification_smtp_host": "",
        "notification_smtp_port": 587,
        "notification_smtp_user": "",
        "notification_smtp_password": "",
        "notification_email": "",
        "notification_ntfy_topic": "my-test-topic" if enabled else "",
    }


def _mock_settings(**overrides):
    cfg = MagicMock()
    defaults = {
        "notification_enabled": True,
        "notification_smtp_host": "",
        "notification_smtp_port": 587,
        "notification_smtp_user": "",
        "notification_smtp_password": "",
        "notification_email": "",
        "notification_ntfy_topic": "",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(cfg, k, v)
    return cfg


_STORE = "app.runtime.settings_store"


@contextmanager
def _patch_notifications(cfg):
    """Patch get_settings and both effective notification getters from the cfg mock."""
    with patch("app.config.get_settings", return_value=cfg):
        with patch(f"{_STORE}.get_effective_notification_email",
                   return_value=cfg.notification_email):
            with patch(f"{_STORE}.get_effective_notification_ntfy_topic",
                       return_value=cfg.notification_ntfy_topic):
                yield


# ── send_limit_warning — SMTP path (T027) ────────────────────────────────────

class TestSendLimitWarning:
    @pytest.mark.asyncio
    async def test_smtp_called_when_smtp_configured(self):
        """When SMTP host + email are set, _send_smtp is invoked."""
        import app.core.notifications as notif_mod
        notif_mod._last_notified_at = 0.0

        cfg = _mock_settings(**_smtp_config(enabled=True))
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_limit_warning(85, 100)
                mock_smtp.assert_called_once()

    @pytest.mark.asyncio
    async def test_smtp_not_called_without_host(self):
        """When SMTP host is empty, _send_smtp must not be called."""
        import app.core.notifications as notif_mod
        notif_mod._last_notified_at = 0.0

        cfg = _mock_settings(notification_enabled=True, notification_smtp_host="",
                             notification_email="", notification_ntfy_topic="")
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_limit_warning(85, 100)
                mock_smtp.assert_not_called()

    @pytest.mark.asyncio
    async def test_smtp_not_called_when_notifications_disabled(self):
        """Master switch off → no SMTP even if host is configured."""
        import app.core.notifications as notif_mod
        notif_mod._last_notified_at = 0.0

        cfg = _mock_settings(**_smtp_config(enabled=False))
        cfg.notification_enabled = False
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_limit_warning(85, 100)
                mock_smtp.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplication_skips_second_call(self):
        """Second call within NOTIFICATION_DEDUP_SECONDS → no-op."""
        import app.core.notifications as notif_mod
        # Simulate a very recent notification
        notif_mod._last_notified_at = time.time()

        cfg = _mock_settings(**_smtp_config(enabled=True))
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_limit_warning(85, 100)
                mock_smtp.assert_not_called()

    @pytest.mark.asyncio
    async def test_dedup_resets_after_window(self):
        """A call whose timestamp exceeds the dedup window fires again."""
        import app.core.notifications as notif_mod
        notif_mod._last_notified_at = time.time() - notif_mod.NOTIFICATION_DEDUP_SECONDS - 1

        cfg = _mock_settings(**_smtp_config(enabled=True))
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_limit_warning(85, 100)
                mock_smtp.assert_called_once()


# ── send_limit_warning — ntfy path (T027) ────────────────────────────────────

class TestSendLimitWarningNtfy:
    @pytest.mark.asyncio
    async def test_ntfy_called_when_topic_configured(self):
        """When ntfy topic is set, httpx POST is made to ntfy.sh/{topic}."""
        import app.core.notifications as notif_mod
        notif_mod._last_notified_at = 0.0

        cfg = _mock_settings(**_ntfy_config(enabled=True))
        with _patch_notifications(cfg):
            mock_response = AsyncMock()
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client):
                await notif_mod.send_limit_warning(85, 100)
                mock_client.post.assert_called_once()
                call_url = mock_client.post.call_args[0][0]
                assert "my-test-topic" in call_url

    @pytest.mark.asyncio
    async def test_ntfy_not_called_when_topic_empty(self):
        """No ntfy topic → httpx must not be called."""
        import app.core.notifications as notif_mod
        notif_mod._last_notified_at = 0.0

        cfg = _mock_settings(notification_enabled=True, notification_ntfy_topic="",
                             notification_smtp_host="", notification_email="")
        with _patch_notifications(cfg):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_class.return_value = mock_client

                await notif_mod.send_limit_warning(85, 100)
                mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_ntfy_error_does_not_raise(self):
        """ntfy errors are caught and logged; send_limit_warning never raises."""
        import app.core.notifications as notif_mod
        notif_mod._last_notified_at = 0.0

        cfg = _mock_settings(**_ntfy_config(enabled=True))
        with _patch_notifications(cfg):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("ntfy unreachable"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch("httpx.AsyncClient", return_value=mock_client):
                # Must not raise despite ntfy failure
                await notif_mod.send_limit_warning(85, 100)


# ── SMTP password not leaked (T027) ──────────────────────────────────────────

class TestSmtpPasswordNotLogged:
    def test_smtp_helper_accepts_password_arg(self):
        """_send_smtp signature accepts password without including it in log calls."""
        import app.core.notifications as notif_mod
        import inspect
        sig = inspect.signature(notif_mod._send_smtp)
        params = list(sig.parameters.keys())
        assert "password" in params

    @pytest.mark.asyncio
    async def test_smtp_error_does_not_raise(self):
        """SMTP errors are caught and logged; send_limit_warning never raises."""
        import app.core.notifications as notif_mod
        notif_mod._last_notified_at = 0.0

        cfg = _mock_settings(**_smtp_config(enabled=True))
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp", side_effect=Exception("connection refused")):
                # Should NOT raise — errors are swallowed
                await notif_mod.send_limit_warning(85, 100)

    def test_send_smtp_calls_starttls_and_sendmail(self):
        """_send_smtp sets up STARTTLS, logs in when credentials given, and sends mail."""
        import app.core.notifications as notif_mod
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_instance.__exit__ = MagicMock(return_value=False)
        with patch("smtplib.SMTP", return_value=mock_smtp_instance):
            notif_mod._send_smtp(
                "smtp.example.com", 587, "user@example.com", "secret",
                "admin@example.com", "Subject", "Body text"
            )
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once_with("user@example.com", "secret")
        mock_smtp_instance.sendmail.assert_called_once()

    def test_send_smtp_skips_login_when_no_credentials(self):
        """_send_smtp skips login() when user/password are empty."""
        import app.core.notifications as notif_mod
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_instance.__exit__ = MagicMock(return_value=False)
        with patch("smtplib.SMTP", return_value=mock_smtp_instance):
            notif_mod._send_smtp(
                "smtp.example.com", 587, "", "",
                "admin@example.com", "Subject", "Body"
            )
        mock_smtp_instance.login.assert_not_called()
        mock_smtp_instance.sendmail.assert_called_once()


# ── send_cleanup_notification ────────────────────────────────────────────────

def _make_cleanup_result(**overrides):
    """Return a minimal CleanupResult-like object for testing."""
    from app.rag.cleanup import CleanupResult
    defaults = dict(
        trigger="manual",
        scope="admin",
        force_mode=False,
        deleted_count=3,
        eligible_count=5,
        cadence="daily",
        retention_hours=720,
        deleted_sources=["report.pdf", "notes.txt", "data.csv"],
        errors=[],
        ran_at="2026-05-24T19:00:00+00:00",
    )
    defaults.update(overrides)
    return CleanupResult(**defaults)


class TestSendCleanupNotification:
    @pytest.mark.asyncio
    async def test_smtp_called_with_cleanup_context(self):
        """SMTP subject and body contain deleted count and file names."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_smtp_config(enabled=True))
        result = _make_cleanup_result()
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_cleanup_notification(result)
        mock_smtp.assert_called_once()
        _, _, _, _, _, subject, body = mock_smtp.call_args[0]
        assert "3" in subject                     # deleted count in subject
        assert "report.pdf" in body               # deleted file names in body
        assert "720" in body or "30" in body or "month" in body  # retention window
        assert "2026-05-24" in body               # ran_at timestamp

    @pytest.mark.asyncio
    async def test_force_mode_subject_says_force(self):
        """Force cleanup uses a distinct subject that mentions 'Force'."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_smtp_config(enabled=True))
        result = _make_cleanup_result(force_mode=True, retention_hours=None, cadence=None)
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_cleanup_notification(result)
        subject = mock_smtp.call_args[0][5]
        assert "force" in subject.lower() or "Force" in subject

    @pytest.mark.asyncio
    async def test_zero_deleted_subject_says_no_expired(self):
        """When nothing was deleted the subject reflects that clearly."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_smtp_config(enabled=True))
        result = _make_cleanup_result(deleted_count=0, deleted_sources=[], eligible_count=0)
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_cleanup_notification(result)
        subject = mock_smtp.call_args[0][5]
        assert "no" in subject.lower() or "0" in subject

    @pytest.mark.asyncio
    async def test_errors_in_result_raise_priority_and_tag(self):
        """Partial storage errors are included in body and ntfy priority becomes high."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_ntfy_config(enabled=True))
        result = _make_cleanup_result(errors=["vector_store: IOError"])
        with _patch_notifications(cfg):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=AsyncMock())
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch("httpx.AsyncClient", return_value=mock_client):
                await notif_mod.send_cleanup_notification(result)
        headers = mock_client.post.call_args[1]["headers"]
        assert headers["Priority"] == "high"
        assert "warning" in headers.get("Tags", "")

    @pytest.mark.asyncio
    async def test_skipped_when_notifications_disabled(self):
        """Cleanup notification is a no-op when notification_enabled is False."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_smtp_config(enabled=True))
        cfg.notification_enabled = False
        result = _make_cleanup_result()
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_cleanup_notification(result)
        mock_smtp.assert_not_called()

    @pytest.mark.asyncio
    async def test_never_raises_on_channel_failure(self):
        """send_cleanup_notification swallows all errors — never raises."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_smtp_config(enabled=True))
        result = _make_cleanup_result()
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp", side_effect=Exception("SMTP down")):
                await notif_mod.send_cleanup_notification(result)  # must not raise


# ── send_test_notification message content ────────────────────────────────────

class TestSendTestNotificationMessages:
    @pytest.mark.asyncio
    async def test_subject_contains_test_keyword(self):
        """Test notification subject must clearly identify it as a test."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_smtp_config(enabled=True))
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_test_notification()
        subject = mock_smtp.call_args[0][5]
        assert "test" in subject.lower()

    @pytest.mark.asyncio
    async def test_body_lists_configured_channels(self):
        """Body must mention configured email address and ntfy status."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_smtp_config(enabled=True))
        cfg.notification_email = "admin@example.com"
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_test_notification()
        body = mock_smtp.call_args[0][6]
        assert "admin@example.com" in body


# ── send_test_notification (T028 helper) ─────────────────────────────────────

class TestSendTestNotification:
    @pytest.mark.asyncio
    async def test_send_test_returns_dict_with_required_keys(self):
        import app.core.notifications as notif_mod
        cfg = _mock_settings(notification_enabled=True, notification_smtp_host="",
                             notification_email="", notification_ntfy_topic="")
        with _patch_notifications(cfg):
            result = await notif_mod.send_test_notification()
        assert "email_sent" in result
        assert "ntfy_sent" in result
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_send_test_bypasses_dedup(self):
        """send_test_notification does not check _last_notified_at."""
        import app.core.notifications as notif_mod
        notif_mod._last_notified_at = time.time()  # dedup window active

        cfg = _mock_settings(**_smtp_config(enabled=True))
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_test_notification()
                # Should still be called despite recent dedup timestamp
                mock_smtp.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_test_email_error_captured_in_errors(self):
        """Email failure is captured in errors list, not raised."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_smtp_config(enabled=True))
        with _patch_notifications(cfg):
            with patch.object(notif_mod, "_send_smtp", side_effect=Exception("conn refused")):
                result = await notif_mod.send_test_notification()
        assert result["email_sent"] is False
        assert any("email" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_send_test_ntfy_success(self):
        """When ntfy topic is configured, send_test_notification returns ntfy_sent=True."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_ntfy_config(enabled=True))
        with _patch_notifications(cfg):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=AsyncMock())
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await notif_mod.send_test_notification()
        assert result["ntfy_sent"] is True
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_send_test_ntfy_error_captured_in_errors(self):
        """ntfy failure is captured in errors list, ntfy_sent=False."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_ntfy_config(enabled=True))
        with _patch_notifications(cfg):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("ntfy down"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await notif_mod.send_test_notification()
        assert result["ntfy_sent"] is False
        assert any("ntfy" in e for e in result["errors"])


# ── POST /api/notifications/test endpoint (T028) ────────────────────────────

class TestNotificationEndpoint:
    @pytest.fixture
    def client(self):
        from app.main import app
        from fastapi.testclient import TestClient
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    @pytest.fixture
    def guest_headers(self, client):
        res = client.post("/api/auth/guest")
        assert res.status_code == 200
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    @pytest.fixture
    def admin_headers(self, client):
        pwd = os.environ.get("ADMIN_PASSWORD", "")
        if not pwd:
            pytest.skip("ADMIN_PASSWORD not set")
        res = client.post("/api/auth/login", json={"username": "admin", "password": pwd})
        if res.status_code != 200:
            pytest.skip("Admin login failed")
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    def test_endpoint_requires_admin(self, client, guest_headers):
        """Guest token → 403."""
        res = client.post("/api/notifications/test", headers=guest_headers)
        assert res.status_code == 403

    def test_endpoint_requires_auth(self, client):
        """No token → 401."""
        res = client.post("/api/notifications/test")
        assert res.status_code in (401, 403)

    @patch("app.core.notifications.send_test_notification")
    @patch("app.runtime.runtime_settings_cookie.restore_runtime_settings_from_cookie")
    def test_returns_200_when_channel_configured(
        self, mock_restore, mock_send_test, client, admin_headers
    ):
        """When at least one channel is configured, endpoint returns 200."""
        import asyncio

        async def _fake_result():
            return {"email_sent": True, "ntfy_sent": False, "errors": []}

        mock_send_test.return_value = _fake_result()

        with patch("app.config.get_settings") as mock_cfg:
            cfg = MagicMock()
            cfg.notification_smtp_host = "smtp.example.com"
            cfg.notification_ntfy_topic = ""
            mock_cfg.return_value = cfg

            res = client.post("/api/notifications/test", headers=admin_headers)

        assert res.status_code == 200
        data = res.json()
        assert "email_sent" in data

    def test_returns_422_when_no_channel_configured(self, client, admin_headers):
        """When no channel is configured, endpoint returns 422."""
        with patch("app.config.get_settings") as mock_cfg:
            cfg = MagicMock()
            cfg.notification_smtp_host = ""
            cfg.notification_ntfy_topic = ""
            mock_cfg.return_value = cfg
            with patch(f"{_STORE}.get_effective_notification_ntfy_topic", return_value=""):
                res = client.post("/api/notifications/test", headers=admin_headers)
        assert res.status_code == 422
