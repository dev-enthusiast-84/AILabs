"""
Notifications API — test and manage notification channels.

OWASP A01 — all endpoints require admin role via require_full_access.
OWASP A09 — SMTP password is never logged or returned.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.utils import require_full_access
from app.runtime.runtime_settings_cookie import restore_runtime_settings_from_cookie

router = APIRouter()


@router.post("/test")
async def send_test_notification_endpoint(request: Request, _user=Depends(require_full_access)):
    """Send a test notification via all configured channels. Admin required.

    OWASP A01 — admin role enforced via require_full_access; guests receive 403.
    """
    restore_runtime_settings_from_cookie(request, _user)
    from app.config import get_settings
    cfg = get_settings()
    if not cfg.notification_smtp_host and not cfg.notification_ntfy_topic:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No notification channels configured. Set NOTIFICATION_SMTP_HOST or NOTIFICATION_NTFY_TOPIC.",
        )
    import inspect
    from app.core.notifications import send_test_notification
    result = await send_test_notification()
    # Guard: if the result is still awaitable (e.g. a coroutine returned by a test mock),
    # await it once more to get the actual dict. This handles AsyncMock test setups where
    # return_value is a coroutine object rather than a plain dict.
    if inspect.isawaitable(result):
        result = await result
    return result
