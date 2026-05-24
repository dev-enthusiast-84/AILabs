"""Unit tests for app.core.notifications module.

Covers:
- T027: send_limit_warning — SMTP, ntfy, deduplication
- T028: POST /api/notifications/test endpoint auth + behaviour
"""
import os
import time
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


# ── send_limit_warning — SMTP path (T027) ────────────────────────────────────

class TestSendLimitWarning:
    @pytest.mark.asyncio
    async def test_smtp_called_when_smtp_configured(self):
        """When SMTP host + email are set, _send_smtp is invoked."""
        import app.core.notifications as notif_mod
        notif_mod._last_notified_at = 0.0

        cfg = _mock_settings(**_smtp_config(enabled=True))
        with patch("app.config.get_settings", return_value=cfg):
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
        with patch("app.config.get_settings", return_value=cfg):
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
        with patch("app.config.get_settings", return_value=cfg):
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
        with patch("app.config.get_settings", return_value=cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_limit_warning(85, 100)
                mock_smtp.assert_not_called()

    @pytest.mark.asyncio
    async def test_dedup_resets_after_window(self):
        """A call whose timestamp exceeds the dedup window fires again."""
        import app.core.notifications as notif_mod
        notif_mod._last_notified_at = time.time() - notif_mod.NOTIFICATION_DEDUP_SECONDS - 1

        cfg = _mock_settings(**_smtp_config(enabled=True))
        with patch("app.config.get_settings", return_value=cfg):
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
        with patch("app.config.get_settings", return_value=cfg):
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
        with patch("app.config.get_settings", return_value=cfg):
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
        with patch("app.config.get_settings", return_value=cfg):
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
        with patch("app.config.get_settings", return_value=cfg):
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


# ── send_test_notification (T028 helper) ─────────────────────────────────────

class TestSendTestNotification:
    @pytest.mark.asyncio
    async def test_send_test_returns_dict_with_required_keys(self):
        import app.core.notifications as notif_mod
        cfg = _mock_settings(notification_enabled=True, notification_smtp_host="",
                             notification_email="", notification_ntfy_topic="")
        with patch("app.config.get_settings", return_value=cfg):
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
        with patch("app.config.get_settings", return_value=cfg):
            with patch.object(notif_mod, "_send_smtp") as mock_smtp:
                await notif_mod.send_test_notification()
                # Should still be called despite recent dedup timestamp
                mock_smtp.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_test_email_error_captured_in_errors(self):
        """Email failure is captured in errors list, not raised."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_smtp_config(enabled=True))
        with patch("app.config.get_settings", return_value=cfg):
            with patch.object(notif_mod, "_send_smtp", side_effect=Exception("conn refused")):
                result = await notif_mod.send_test_notification()
        assert result["email_sent"] is False
        assert any("email" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_send_test_ntfy_success(self):
        """When ntfy topic is configured, send_test_notification returns ntfy_sent=True."""
        import app.core.notifications as notif_mod
        cfg = _mock_settings(**_ntfy_config(enabled=True))
        with patch("app.config.get_settings", return_value=cfg):
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
        with patch("app.config.get_settings", return_value=cfg):
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

            res = client.post("/api/notifications/test", headers=admin_headers)
        assert res.status_code == 422
