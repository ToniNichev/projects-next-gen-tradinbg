"""
Authentication module for the trading bot dashboard.

Supports both Basic HTTP Authentication and API Key authentication.
"""

import logging
import os
from functools import wraps
from typing import Optional

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


@http_auth.verify_password
def verify_password(username: str, password: str) -> bool:
    """Verify username and password for Basic HTTP Auth"""
    config = get_auth_config()
    
    # If auth is disabled, allow all
    if not config.enabled:
        return True
    
    # Check username matches
    if username != config.username:
        logger.warning(f"Authentication failed: invalid username '{username}'")
        return False
    
    # Check if stored password is hashed (starts with $2b$ for bcrypt)
    if config.password.startswith('$2b$') or config.password.startswith('$2a$'):
        # Stored password is hashed, verify with bcrypt
        is_valid = config.verify_password(password, config.password)
    else:
        # Stored password is plaintext (for development), compare directly
        is_valid = password == config.password
    
    if not is_valid:
        logger.warning(f"Authentication failed: invalid password for user '{username}'")
    
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


# Log authentication status on module import
config = get_auth_config()
if config.enabled:
    logger.info("Dashboard authentication is ENABLED")
    logger.info(f"Username: {config.username}")
    if config.password == "changeme":
        logger.warning("⚠️  Using default password! Set DASHBOARD_PASSWORD for production!")
else:
    logger.warning("Dashboard authentication is DISABLED - all endpoints are public!")





