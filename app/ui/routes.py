"""
UI Routes Module

This module handles HTML page rendering and template-based routes for the trading bot web interface.
All routes use the @require_auth decorator for authentication and render templates from the templates/ directory.

Routes:
- / : Home redirect to /ui
- /ui : Main trading dashboard
- /backtest : Backtest page
- /strategies : Strategies configuration page
- /settings : Settings page
- /logout : Logout handler
"""

from flask import Blueprint, render_template, redirect, url_for, request, jsonify, make_response, Response
import logging

# Try to import auth decorator
try:
    from auth import require_auth
    AUTH_AVAILABLE = True
except ImportError:
    # Create a no-op decorator if auth is not available
    def require_auth(f):
        return f
    AUTH_AVAILABLE = False

# Create UI blueprint with no url_prefix (root level)
ui_bp = Blueprint('ui', __name__)

logger = logging.getLogger(__name__)


@ui_bp.route('/')
@require_auth
def home():
    """
    Home page - redirects to main dashboard UI
    
    Validates: Requirements 15.1
    """
    logger.debug("Home route accessed, redirecting to /ui")
    return redirect(url_for('ui.get_ui'))


@ui_bp.route('/ui')
@require_auth
def get_ui():
    """
    Main trading dashboard page
    
    Renders the main UI template with trading dashboard interface.
    
    Validates: Requirements 15.2, 15.7
    """
    logger.debug("Rendering main UI dashboard")
    return render_template("ui.html")


@ui_bp.route('/backtest')
@require_auth
def backtest_page():
    """
    Backtest page
    
    Renders the backtest interface for running and viewing backtests.
    
    Validates: Requirements 15.3, 15.7
    """
    logger.debug("Rendering backtest page")
    return render_template("backtest.html")


@ui_bp.route('/strategies')
@require_auth
def strategies_page():
    """
    Strategies configuration page
    
    Renders the strategies configuration interface.
    
    Validates: Requirements 15.4, 15.7
    """
    logger.debug("Rendering strategies page")
    return render_template("strategy_config.html")


@ui_bp.route('/settings')
@require_auth
def settings_page():
    """
    Settings page
    
    Renders the settings/configuration interface.
    Note: Currently uses strategy_config.html as the settings template.
    
    Validates: Requirements 15.5, 15.7
    """
    logger.debug("Rendering settings page")
    # Using strategy_config.html as settings template since settings.html doesn't exist yet
    return render_template("strategy_config.html")


@ui_bp.route('/logout')
def logout():
    """
    Logout handler
    
    Handles user logout by displaying logout page with instructions.
    Note: HTTP Basic Auth credentials are cached by the browser,
    so complete logout requires closing all browser windows.
    
    For API requests (JSON), returns a JSON response.
    For browser requests, renders the logout template.
    
    Validates: Requirements 15.6, 15.8, 15.9
    """
    logger.info("Logout route accessed")
    
    # If this is an API request (JSON), return JSON response
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({
            "message": "Logged out successfully",
            "note": "For API key auth, simply stop sending the key. For Basic Auth, close all browser windows."
        }), 200
    
    # For browser requests, show the logout page
    response = make_response(render_template("logout.html"))
    
    # Add headers to prevent caching of the logout page
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response


@ui_bp.route('/logout/clear')
def logout_clear():
    """
    Logout clear endpoint
    
    Returns 401 to force browser to clear Basic Auth credentials.
    This is called by JavaScript from the logout page.
    
    Validates: Requirements 15.9
    """
    logger.debug("Logout clear endpoint accessed")
    
    # Return 401 with WWW-Authenticate to clear browser auth cache
    response = Response(
        'Authentication cleared. Please close all browser windows for complete logout.',
        401,
        {'WWW-Authenticate': 'Basic realm="Dashboard Login Required"'}
    )
    
    return response
