"""
Shared Flask extensions.

Initialised here without an app so they can be imported by any blueprint.
Call ``init_extensions(app)`` from the application factory after the app
is created.
"""

from flask import request
from flask_limiter import Limiter


def _get_real_ip() -> str:
    # Apache mod_proxy sets X-Forwarded-For to the real client IP.
    # Take the leftmost entry to guard against spoofing a second hop.
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


limiter = Limiter(
    key_func=_get_real_ip,
    default_limits=["60 per minute"],
    storage_uri="memory://",
)


def init_extensions(app) -> None:
    """Bind all extensions to the Flask app instance."""
    limiter.init_app(app)


# ---------------------------------------------------------------------------
# Auth helper (re-exported so blueprints only need one import)
# ---------------------------------------------------------------------------

try:
    from auth import require_auth  # noqa: F401
except ImportError:
    import logging as _logging
    _logging.warning("auth module not available — all endpoints will be unsecured")

    def require_auth(f):  # type: ignore[misc]
        return f
