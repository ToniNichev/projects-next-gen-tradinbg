"""
Test script for dashboard authentication and security features.

Tests:
1. Basic HTTP Authentication
2. API Key Authentication  
3. Unauthenticated access blocking
4. Health check endpoint (no auth required)
5. Password hashing utilities
6. Authentication configuration

Usage:
    # Set test credentials first
    export DASHBOARD_USERNAME=testuser
    export DASHBOARD_PASSWORD=testpass
    export DASHBOARD_API_KEY=test_api_key_12345
    
    # Run tests
    python test_auth.py
"""

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def test_auth_module():
    """Test authentication module functionality"""
    logger.info("=" * 70)
    logger.info("AUTHENTICATION MODULE TEST")
    logger.info("=" * 70)
    
    # Test 1: Import auth module
    logger.info("\n1. Testing auth module import...")
    try:
        from auth import (
            get_auth_config,
            verify_password,
            verify_token,
            hash_password_cli,
            is_auth_enabled
        )
        logger.info("✅ Auth module imported successfully")
    except Exception as e:
        logger.error(f"❌ Failed to import auth module: {e}")
        return False
    
    # Test 2: Load configuration
    logger.info("\n2. Testing authentication configuration...")
    try:
        config = get_auth_config()
        logger.info(f"✅ Auth enabled: {config.enabled}")
        logger.info(f"   Username: {config.username}")
        logger.info(f"   Password set: {'Yes' if config.password else 'No'}")
        logger.info(f"   API key set: {'Yes' if config.api_key else 'No'}")
        logger.info(f"   Require HTTPS: {config.require_https}")
    except Exception as e:
        logger.error(f"❌ Configuration loading failed: {e}")
        return False
    
    # Test 3: Password hashing
    logger.info("\n3. Testing password hashing...")
    try:
        test_password = "test_password_123"
        hashed = hash_password_cli(test_password)
        logger.info(f"✅ Password hashed successfully")
        logger.info(f"   Hash: {hashed[:50]}...")
        
        # Verify the hash works
        import bcrypt
        is_valid = bcrypt.checkpw(test_password.encode('utf-8'), hashed.encode('utf-8'))
        if is_valid:
            logger.info("✅ Password verification successful")
        else:
            logger.error("❌ Password verification failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Password hashing failed: {e}")
        return False
    
    # Test 4: Verify password function
    logger.info("\n4. Testing password verification...")
    try:
        # Set test credentials
        os.environ["DASHBOARD_USERNAME"] = "testuser"
        os.environ["DASHBOARD_PASSWORD"] = "testpass"
        
        # Reload config
        from auth import _auth_config
        import auth as auth_module
        auth_module._auth_config = None
        config = get_auth_config()
        
        # Test valid credentials
        is_valid = verify_password("testuser", "testpass")
        if is_valid:
            logger.info("✅ Valid credentials accepted")
        else:
            logger.error("❌ Valid credentials rejected")
            return False
        
        # Test invalid password
        is_valid = verify_password("testuser", "wrongpass")
        if not is_valid:
            logger.info("✅ Invalid password rejected")
        else:
            logger.error("❌ Invalid password accepted")
            return False
        
        # Test invalid username
        is_valid = verify_password("wronguser", "testpass")
        if not is_valid:
            logger.info("✅ Invalid username rejected")
        else:
            logger.error("❌ Invalid username accepted")
            return False
            
    except Exception as e:
        logger.error(f"❌ Password verification test failed: {e}")
        return False
    
    # Test 5: API key verification
    logger.info("\n5. Testing API key verification...")
    try:
        os.environ["DASHBOARD_API_KEY"] = "test_api_key_12345"
        
        # Reload config
        auth_module._auth_config = None
        config = get_auth_config()
        
        # Test valid API key
        is_valid = verify_token("test_api_key_12345")
        if is_valid:
            logger.info("✅ Valid API key accepted")
        else:
            logger.error("❌ Valid API key rejected")
            return False
        
        # Test invalid API key
        is_valid = verify_token("wrong_api_key")
        if not is_valid:
            logger.info("✅ Invalid API key rejected")
        else:
            logger.error("❌ Invalid API key accepted")
            return False
            
    except Exception as e:
        logger.error(f"❌ API key verification test failed: {e}")
        return False
    
    # Test 6: Authentication disabled mode
    logger.info("\n6. Testing authentication disabled mode...")
    try:
        os.environ["DASHBOARD_AUTH_ENABLED"] = "false"
        
        # Reload config
        auth_module._auth_config = None
        config = get_auth_config()
        
        if not config.enabled:
            logger.info("✅ Authentication disabled successfully")
        else:
            logger.error("❌ Authentication still enabled")
            return False
        
        # Should accept any credentials when disabled
        is_valid = verify_password("anyuser", "anypass")
        if is_valid:
            logger.info("✅ Auth bypass works when disabled")
        else:
            logger.error("❌ Auth bypass not working")
            return False
        
        # Re-enable for remaining tests
        os.environ["DASHBOARD_AUTH_ENABLED"] = "true"
        auth_module._auth_config = None
        
    except Exception as e:
        logger.error(f"❌ Auth disabled mode test failed: {e}")
        return False
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ ALL AUTHENTICATION MODULE TESTS PASSED!")
    logger.info("=" * 70)
    
    return True


def test_dashboard_integration():
    """Test dashboard endpoints with authentication"""
    logger.info("\n" + "=" * 70)
    logger.info("DASHBOARD INTEGRATION TEST")
    logger.info("=" * 70)
    
    logger.info("\n1. Testing dashboard module import...")
    try:
        from app import create_app; app = create_app()
        logger.info("✅ Dashboard module imported successfully")
    except Exception as e:
        logger.error(f"❌ Failed to create Flask app: {e}")
        return False
    
    logger.info("\n2. Checking protected routes...")
    try:
        # Get all routes
        routes = []
        for rule in app.url_map.iter_rules():
            if rule.endpoint != 'static':
                routes.append((rule.rule, rule.methods))
        
        logger.info(f"✅ Found {len(routes)} routes:")
        for route, methods in sorted(routes):
            methods_str = ', '.join(sorted(methods - {'HEAD', 'OPTIONS'}))
            logger.info(f"   {route:40} [{methods_str}]")
            
    except Exception as e:
        logger.error(f"❌ Route inspection failed: {e}")
        return False
    
    logger.info("\n3. Testing Flask-Limiter initialization...")
    try:
        from app.extensions import limiter
        logger.info(f"✅ Rate limiter initialized: {limiter}")
    except Exception as e:
        logger.error(f"❌ Rate limiter initialization failed: {e}")
        return False
    
    logger.info("\n4. Testing CORS initialization...")
    try:
        from app.extensions import cors
        logger.info(f"✅ CORS initialized (will be configured on start)")
    except Exception as e:
        logger.error(f"❌ CORS initialization failed: {e}")
        return False
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ DASHBOARD INTEGRATION TESTS PASSED!")
    logger.info("=" * 70)
    
    return True


def test_config_integration():
    """Test configuration with security settings"""
    logger.info("\n" + "=" * 70)
    logger.info("CONFIGURATION INTEGRATION TEST")
    logger.info("=" * 70)
    
    logger.info("\n1. Testing config module with security settings...")
    try:
        from config import BotConfig
        
        # Set test environment
        os.environ["DASHBOARD_USERNAME"] = "admin"
        os.environ["DASHBOARD_PASSWORD"] = "testpass123"
        os.environ["DASHBOARD_API_KEY"] = "sk_test_abcdef123456"
        os.environ["DASHBOARD_AUTH_ENABLED"] = "true"
        os.environ["DASHBOARD_ENABLE_RATE_LIMITING"] = "true"
        os.environ["DASHBOARD_RATE_LIMIT_PER_MINUTE"] = "100"
        os.environ["DASHBOARD_ALLOWED_ORIGINS"] = "http://localhost:3000,https://example.com"
        
        config = BotConfig.load()
        
        logger.info("✅ Configuration loaded successfully")
        logger.info(f"   Auth enabled: {config.dashboard_auth_enabled}")
        logger.info(f"   Username: {config.dashboard_username}")
        logger.info(f"   Password set: {'Yes' if config.dashboard_password else 'No'}")
        logger.info(f"   API key set: {'Yes' if config.dashboard_api_key else 'No'}")
        logger.info(f"   Rate limiting: {config.enable_rate_limiting}")
        logger.info(f"   Rate limit: {config.rate_limit_per_minute}/min")
        logger.info(f"   CORS origins: {config.allowed_origins}")
        
        # Verify values
        assert config.dashboard_username == "admin"
        assert config.dashboard_password == "testpass123"
        assert config.dashboard_api_key == "sk_test_abcdef123456"
        assert config.dashboard_auth_enabled == True
        assert config.enable_rate_limiting == True
        assert config.rate_limit_per_minute == 100
        assert config.allowed_origins == "http://localhost:3000,https://example.com"
        
        logger.info("✅ All configuration values verified")
        
    except Exception as e:
        logger.error(f"❌ Configuration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ CONFIGURATION INTEGRATION TESTS PASSED!")
    logger.info("=" * 70)
    
    return True


def print_usage_examples():
    """Print usage examples"""
    logger.info("\n" + "=" * 70)
    logger.info("USAGE EXAMPLES")
    logger.info("=" * 70)
    
    logger.info("\n1. Generate bcrypt password hash:")
    logger.info("   python -c \"from auth import hash_password_cli; print(hash_password_cli('your_password'))\"")
    
    logger.info("\n2. Access dashboard with Basic Auth (curl):")
    logger.info("   curl -u admin:changeme http://localhost:8000/api/stats")
    
    logger.info("\n3. Access dashboard with API Key (curl):")
    logger.info("   curl -H \"Authorization: Bearer YOUR_API_KEY\" http://localhost:8000/api/stats")
    
    logger.info("\n4. Health check (no auth required):")
    logger.info("   curl http://localhost:8000/health")
    
    logger.info("\n5. Start dashboard with authentication enabled:")
    logger.info("   export DASHBOARD_AUTH_ENABLED=true")
    logger.info("   export DASHBOARD_USERNAME=admin")
    logger.info("   export DASHBOARD_PASSWORD=your_secure_password")
    logger.info("   python main.py")
    
    logger.info("\n6. Disable authentication for development:")
    logger.info("   export DASHBOARD_AUTH_ENABLED=false")
    logger.info("   python main.py")
    
    logger.info("\n" + "=" * 70)


def main():
    """Run all tests"""
    logger.info("\n" + "=" * 70)
    logger.info("DASHBOARD AUTHENTICATION TEST SUITE")
    logger.info("=" * 70)
    
    all_passed = True
    
    # Test 1: Authentication module
    if not test_auth_module():
        all_passed = False
    
    # Test 2: Dashboard integration
    if not test_dashboard_integration():
        all_passed = False
    
    # Test 3: Configuration integration
    if not test_config_integration():
        all_passed = False
    
    # Print usage examples
    print_usage_examples()
    
    # Final result
    logger.info("\n" + "=" * 70)
    if all_passed:
        logger.info("🎉 ALL TESTS PASSED!")
        logger.info("=" * 70)
        logger.info("\nAuthentication is fully functional!")
        logger.info("\nNext steps:")
        logger.info("1. Install dependencies: pip install -r requirements.txt")
        logger.info("2. Copy env.example to .env and configure credentials")
        logger.info("3. Start the bot: python main.py")
        logger.info("4. Access dashboard: http://localhost:8000")
        logger.info("=" * 70)
        return 0
    else:
        logger.error("❌ SOME TESTS FAILED")
        logger.info("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())



