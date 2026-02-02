#!/usr/bin/env python3
"""
Migration script to add preset functionality to existing database.
Run this after updating the codebase to add the strategy presets feature.
"""

import logging
from database import initialize_database, get_database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Run the migration"""
    try:
        logger.info("Starting preset migration...")
        
        # Initialize database (this will create missing tables)
        logger.info("Initializing database...")
        db = initialize_database()
        
        # The create_tables() call automatically initializes built-in presets
        logger.info("Migration complete!")
        logger.info("Built-in presets have been initialized:")
        
        # List presets
        presets = db.get_all_presets()
        for preset in presets:
            logger.info(f"  - {preset['display_name']} ({preset['category']})")
        
        logger.info("\n✅ Migration successful! You can now use presets in the Strategy Center.")
        logger.info("   Navigate to http://localhost:8000/strategy-config to try them out.")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
