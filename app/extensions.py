"""
Shared Flask extensions.

Initialised here without an app so they can be imported by any blueprint.
Call ``init_extensions(app)`` from the application factory after the app
is created.
"""

from urllib.parse import urlparse

from flask import request
from flask_limiter import Limiter


def _get_real_ip() -> str:
    # Apache mod_proxy sets X-Forwarded-For to the real client IP.
    # Take the leftmost entry to guard against spoofing a second hop.
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def _default_rate_limit() -> str:
    # Evaluated per-request so DASHBOARD_RATE_LIMIT_PER_MINUTE takes effect
    # without needing the limiter to be reconstructed.
    from config import BotConfig
    return f"{BotConfig.load().rate_limit_per_minute} per minute"


limiter = Limiter(
    key_func=_get_real_ip,
    default_limits=[_default_rate_limit],
    storage_uri="memory://",
)


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _own_hosts() -> set:
    """Host names this dashboard is reached under (directly or via the proxy)."""
    hosts = {request.host.lower()}
    fwd = request.headers.get("X-Forwarded-Host", "")
    hosts.update(h.strip().lower() for h in fwd.split(",") if h.strip())
    try:
        from config import BotConfig
        for o in (BotConfig.load().allowed_origins or "").split(","):
            o = o.strip()
            if o and o != "*":
                hosts.add(urlparse(o).netloc.lower() or o.lower())
    except Exception:
        pass
    return hosts


def cross_site_refusal():
    """Refuse a money-changing request sent by another website.

    The browser re-sends the dashboard login with any request, even one a
    different site makes it send (a hidden form posting to emergency-stop,
    manual sell, ...). Browsers always say where such a request comes from
    (Origin, or at least Referer), so a write from a page that isn't this
    dashboard is refused. Scripts and the API key (curl, the watchdog) send
    neither header and are let through to the normal login check.
    """
    if request.method in SAFE_METHODS:
        return None
    source = request.headers.get("Origin") or request.headers.get("Referer")
    if not source:
        return None
    host = urlparse(source).netloc.lower()
    if host and host in _own_hosts():
        return None
    import logging
    logging.getLogger(__name__).warning(
        "Refused %s %s from another website (%s)", request.method, request.path, source[:100])
    return {"success": False, "error": "Refused: this request came from another website"}, 403


def init_extensions(app) -> None:
    """Bind all extensions to the Flask app instance."""
    limiter.init_app(app)
    app.before_request(cross_site_refusal)


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
