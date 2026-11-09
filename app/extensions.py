"""
Shared Flask extensions.

Initialised here without an app so they can be imported by any blueprint.
Call ``init_extensions(app)`` from the application factory after the app
is created.
"""

from urllib.parse import urlparse

from flask import request
import ipaddress

from flask_limiter import Limiter


# Cloudflare's published edge ranges (cloudflare.com/ips). The site is
# visitor -> Cloudflare -> Apache on this Mac -> the bot.
_CLOUDFLARE_NETS = [ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
    "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
    "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
)]


def _is_cloudflare(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _CLOUDFLARE_NETS)


def _is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def client_ip_from(remote_addr: str, forwarded_for: str) -> str:
    """The visitor's real address. X-Forwarded-For is read from the RIGHT:
    each proxy appends the address that connected to it, while the left part
    is whatever the visitor sent (and can be faked to dodge the login lockout).
    Apache adds the last entry; when that is a Cloudflare edge, the entry
    before it is the one Cloudflare added: the visitor."""
    remote = remote_addr or "127.0.0.1"
    if not _is_loopback(remote):
        return remote  # reached the bot directly, not through Apache
    parts = [p.strip() for p in (forwarded_for or "").split(",") if p.strip()]
    if not parts:
        return remote
    peer = parts[-1]
    if _is_cloudflare(peer) and len(parts) >= 2:
        return parts[-2]
    return peer


def _get_real_ip() -> str:
    return client_ip_from(request.remote_addr, request.headers.get("X-Forwarded-For", ""))


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
