"""
Authentication module for the trading bot dashboard.

Supports both Basic HTTP Authentication and API Key authentication.
"""

import logging
import os
import threading
import time
from functools import wraps
from typing import Dict, List, Optional

import bcrypt
from flask import request
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth

logger = logging.getLogger(__name__)

# Initialize authentication handlers
http_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth(scheme='Bearer')
multi_auth = MultiAuth(http_auth, token_auth)


class AuthConfig:
    """Authentication configuration loaded from environment variables"""
    
    def __init__(self):
        self.enabled = os.environ.get("DASHBOARD_AUTH_ENABLED", "true").lower() == "true"
        self.username = os.environ.get("DASHBOARD_USERNAME", "admin")
        self.password = os.environ.get("DASHBOARD_PASSWORD", "")
        self.api_key = os.environ.get("DASHBOARD_API_KEY", "")
        
        # Security settings
        self.require_https = os.environ.get("DASHBOARD_REQUIRE_HTTPS", "false").lower() == "true"
        
        # Generate default password if none provided (for development)
        if not self.password:
            logger.warning(
                "No DASHBOARD_PASSWORD set. Using default password 'changeme'. "
                "Set DASHBOARD_PASSWORD environment variable for production!"
            )
            self.password = "changeme"
        
        # Generate default API key if none provided
        if not self.api_key:
            logger.warning(
                "No DASHBOARD_API_KEY set. API key authentication will use username:password format. "
                "Set DASHBOARD_API_KEY environment variable for dedicated API access!"
            )
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against a bcrypt hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False


# Global auth config instance
_auth_config: Optional[AuthConfig] = None


def get_auth_config() -> AuthConfig:
    """Get or create the authentication configuration"""
    global _auth_config
    if _auth_config is None:
        _auth_config = AuthConfig()
    return _auth_config


# Brute-force lockout: too many failed logins from one IP blocks it for a while.
LOCKOUT_MAX_FAILURES = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60
_failed_logins: Dict[str, List[float]] = {}
_failed_lock = threading.Lock()


def _client_ip() -> str:
    try:
        from app.extensions import _get_real_ip
        return _get_real_ip()
    except Exception:
        return request.remote_addr or "unknown"


def _recent_failures(ip: str, now: float) -> List[float]:
    """Failures from this IP inside the window (caller holds the lock)."""
    recent = [t for t in _failed_logins.get(ip, []) if now - t < LOCKOUT_WINDOW_SECONDS]
    if recent:
        _failed_logins[ip] = recent
    else:
        _failed_logins.pop(ip, None)
    return recent


def _is_locked_out(ip: str) -> bool:
    with _failed_lock:
        return len(_recent_failures(ip, time.time())) >= LOCKOUT_MAX_FAILURES


def _record_failure(ip: str) -> None:
    with _failed_lock:
        now = time.time()
        recent = _recent_failures(ip, now)
        recent.append(now)
        _failed_logins[ip] = recent
        if len(recent) == LOCKOUT_MAX_FAILURES:
            logger.warning(
                "Locking out %s for %d min after %d failed logins",
                ip, LOCKOUT_WINDOW_SECONDS // 60, LOCKOUT_MAX_FAILURES,
            )


@http_auth.verify_password
def verify_password(username: str, password: str) -> bool:
    """Verify username and password for Basic HTTP Auth"""
    config = get_auth_config()

    # If auth is disabled, allow all
    if not config.enabled:
        return True

    # No credentials sent (e.g. a browser's first request before the login
    # prompt). Not a failed attempt, so don't log or count it.
    if not username and not password:
        return False

    ip = _client_ip()
    if _is_locked_out(ip):
        logger.warning(f"Authentication blocked: {ip} is locked out")
        return False

    # Check username matches
    if username != config.username:
        logger.warning(f"Authentication failed: invalid username '{username}' from {ip}")
        _record_failure(ip)
        return False

    # Check if stored password is hashed (starts with $2b$ for bcrypt)
    if config.password.startswith('$2b$') or config.password.startswith('$2a$'):
        # Stored password is hashed, verify with bcrypt
        is_valid = config.verify_password(password, config.password)
    else:
        # Stored password is plaintext (for development), compare directly
        is_valid = password == config.password
    
    if not is_valid:
        logger.warning(f"Authentication failed: invalid password for user '{username}' from {ip}")
        _record_failure(ip)

    return is_valid


@token_auth.verify_token
def verify_token(token: str) -> bool:
    """Verify API key token for Bearer token auth"""
    config = get_auth_config()
    
    # If auth is disabled, allow all
    if not config.enabled:
        return True
    
    # Check if token matches configured API key
    if config.api_key and token == config.api_key:
        return True
    
    logger.warning("Authentication failed: invalid API key")
    return False


def require_auth(f):
    """
    Decorator to require authentication for a route.
    Supports both Basic HTTP Auth and API Key authentication.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        config = get_auth_config()
        
        # If auth is disabled, skip authentication
        if not config.enabled:
            return f(*args, **kwargs)
        
        # Check for HTTPS in production
        if config.require_https and not request.is_secure:
            logger.warning("Rejected non-HTTPS request")
            return {"error": "HTTPS required"}, 403
        
        # Use multi_auth to support both Basic and Token auth
        return multi_auth.login_required(f)(*args, **kwargs)
    
    return decorated_function


def get_current_user() -> Optional[str]:
    """Get the currently authenticated user (if any)"""
    config = get_auth_config()
    
    if not config.enabled:
        return "anonymous"
    
    # Check for Basic Auth
    auth = request.authorization
    if auth and auth.username:
        return auth.username
    
    # Check for Bearer token
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return "api_key_user"
    
    return None


def hash_password_cli(password: str) -> str:
    """
    Utility function to hash a password for use in environment variable.
    
    Usage:
        python -c "from auth import hash_password_cli; print(hash_password_cli('your_password'))"
    """
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def is_auth_enabled() -> bool:
    """Check if authentication is enabled"""
    config = get_auth_config()
    return config.enabled


def enforce_production_auth(bot_config) -> None:
    """
    Refuse to start in a non-paper trading mode without real dashboard auth.

    Paper mode keeps today's permissive, dev-friendly defaults (auth may be
    disabled; a missing password silently becomes "changeme"). Once the bot
    can log real signals against a live account (dry_run) or place real
    orders (live), those soft defaults would leave manual-trade and
    emergency-stop endpoints unauthenticated or behind a well-known
    password, so this raises a hard, fail-closed error instead.
    """
    trading_mode = getattr(bot_config, "trading_mode", "paper")
    if trading_mode == "paper":
        return

    auth_config = get_auth_config()

    if not auth_config.enabled:
        logger.critical(
            "Refusing to start in '%s' mode: DASHBOARD_AUTH_ENABLED is disabled. "
            "Set DASHBOARD_AUTH_ENABLED=true before running non-paper trading modes.",
            trading_mode,
        )
        raise SystemExit(1)

    if not auth_config.password or auth_config.password == "changeme":
        logger.critical(
            "Refusing to start in '%s' mode: DASHBOARD_PASSWORD is unset or left at "
            "the default 'changeme'. Set a real DASHBOARD_PASSWORD before running "
            "non-paper trading modes.",
            trading_mode,
        )
        raise SystemExit(1)


# Log authentication status on module import
config = get_auth_config()
if config.enabled:
    logger.info("Dashboard authentication is ENABLED")
    logger.info(f"Username: {config.username}")
    if config.password == "changeme":
        logger.warning("⚠️  Using default password! Set DASHBOARD_PASSWORD for production!")
else:
    logger.warning("Dashboard authentication is DISABLED - all endpoints are public!")








