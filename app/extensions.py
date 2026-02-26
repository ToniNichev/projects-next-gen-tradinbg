"""
Shared Flask extensions.

Initialised here without an app so they can be imported by any blueprint.
Call ``init_extensions(app)`` from the application factory after the app
is created.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
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
