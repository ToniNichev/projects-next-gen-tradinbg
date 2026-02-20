# Implementation Plan: Code Organization Refactor

## Overview

This implementation plan transforms the monolithic trading bot codebase into a well-structured, maintainable architecture with clear separation of concerns. The refactoring follows a phased approach to ensure safety and backward compatibility, creating new modules alongside existing code before gradually migrating functionality.

## Tasks

- [x] 1. Create directory structure and core interfaces
  - Create app/api/, app/ui/, app/core/, app/services/, tests/unit/, tests/integration/, tests/property/ directories
  - Create __init__.py files for all packages
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.10_

- [x] 2. Implement Application State Manager
  - [x] 2.1 Create TradingState and BacktestState dataclasses in app/core/state.py
    - Implement TradingState with all required fields and validation
    - Implement BacktestState with progress tracking fields
    - _Requirements: 2.7, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_
  
  - [x] 2.2 Implement ApplicationState class with thread-safe operations
    - Implement singleton pattern with get_app_state() function
    - Implement thread-safe state getters and setters using locks
    - Implement trader instance management methods
    - Implement history management with rolling window
    - Implement backtest result storage with size limits
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.8, 16.1, 16.2, 16.5, 16.6, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 18.8_
  
  - [x]* 2.3 Write property test for state consistency
    - **Property 1: State Consistency**
    - **Validates: Requirements 2.2, 2.3, 2.4, 8.10, 8.11**
    - Test concurrent state updates maintain consistency
  
  - [ ]* 2.4 Write unit tests for ApplicationState
    - Test singleton pattern enforcement
    - Test thread-safe state updates
    - Test history management and rolling window
    - Test trader instance lifecycle
    - _Requirements: 9.4_

- [x] 3. Implement Configuration Service
  - [x] 3.1 Create ConfigService class in app/services/config_service.py
    - Implement load_config() with database fallback to environment
    - Implement configuration caching mechanism
    - Implement validation logic for all configuration fields
    - Implement preset management (save, load, apply, delete)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 6.12, 6.13, 6.14, 10.5, 10.6, 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7_
  
  - [ ]* 3.2 Write property test for configuration validation
    - **Property 3: Configuration Validation**
    - **Validates: Requirements 6.5, 6.6, 6.9, 6.10, 6.11**
    - Test that invalid configurations are always rejected
  
  - [ ]* 3.3 Write unit tests for ConfigService
    - Test configuration loading with database and fallback
    - Test validation for all field types
    - Test preset management operations
    - Test cache invalidation on updates
    - _Requirements: 9.7_

- [x] 4. Implement Trading Manager
  - [x] 4.1 Create TradingManager class in app/services/trading_manager.py
    - Implement execute_manual_buy() with validation and state updates
    - Implement execute_manual_sell() with validation and state updates
    - Implement enable_trading() and disable_trading()
    - Implement trigger_emergency_stop() with position closing
    - Implement sync_exchange_state() for balance synchronization
    - Implement get_current_price() and create_manual_signal()
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 17.8, 20.1, 20.2, 20.3, 20.4, 20.5_
  
  - [ ]* 4.2 Write property test for trade execution atomicity
    - **Property 4: Trade Execution Atomicity**
    - **Validates: Requirements 4.3, 4.4, 4.5, 4.6, 4.7, 8.7, 8.8**
    - Test that trades either fully succeed or fully fail with no partial state
  
  - [ ]* 4.3 Write unit tests for TradingManager
    - Test manual buy and sell operations
    - Test trading enable/disable
    - Test emergency stop functionality
    - Test error handling for invalid inputs
    - Test state updates after successful trades
    - _Requirements: 9.5_

- [x] 5. Implement Backtest Manager
  - [x] 5.1 Create BacktestManager class in app/services/backtest_manager.py
    - Implement run_backtest() with progress tracking and callbacks
    - Implement get_backtest_status() for progress queries
    - Implement get_backtest_results() and get_backtest_result()
    - Implement clear_backtest_results()
    - Implement update_progress() for state updates
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7_
  
  - [ ]* 5.2 Write property test for backtest progress monotonicity
    - **Property 6: Backtest Progress Monotonicity**
    - **Validates: Requirements 5.3, 5.4, 5.5, 5.6**
    - Test that progress always increases from 0.0 to 1.0
  
  - [ ]* 5.3 Write unit tests for BacktestManager
    - Test backtest execution with various parameters
    - Test progress tracking and callbacks
    - Test result storage and retrieval
    - Test error handling during backtest
    - _Requirements: 9.6_

- [ ] 6. Checkpoint - Ensure all service layer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement API Routes Module
  - [x] 7.1 Create API blueprint in app/api/routes.py
    - Implement health check endpoint (/api/health)
    - Implement state retrieval endpoint (/api/state)
    - Implement manual trading endpoints (/api/manual/buy, /api/manual/sell)
    - Implement trading control endpoints (/api/trading/enable, /api/trading/disable)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  
  - [x] 7.2 Implement configuration endpoints in app/api/routes.py
    - Implement configuration retrieval endpoint (/api/config)
    - Implement strategy configuration endpoint (/api/config/strategy)
    - _Requirements: 3.7, 3.8_
  
  - [x] 7.3 Implement backtest endpoints in app/api/routes.py
    - Implement backtest execution endpoint (/api/backtest/run)
    - Implement backtest status endpoint (/api/backtest/status)
    - Implement backtest results endpoint (/api/backtest/results)
    - _Requirements: 3.9, 3.10, 3.11_
  
  - [x] 7.4 Implement APIResponse standardization
    - Create APIResponse dataclass in app/api/routes.py
    - Ensure all endpoints return standardized format
    - Implement error handling with structured responses
    - _Requirements: 3.12, 3.13, 3.14, 7.13, 7.14, 7.15_
  
  - [ ]* 7.5 Write property test for API response consistency
    - **Property 2: API Response Consistency**
    - **Validates: Requirements 3.12, 3.13, 3.14, 7.13, 7.14, 7.15**
    - Test that all endpoints return standardized APIResponse format
  
  - [ ]* 7.6 Write unit tests for API routes
    - Test all endpoint request/response formats
    - Test authentication and authorization
    - Test input validation
    - Test error responses
    - _Requirements: 9.8_

- [x] 8. Implement UI Routes Module
  - [x] 8.1 Create UI blueprint in app/ui/routes.py
    - Implement home redirect (/)
    - Implement main dashboard (/ui)
    - Implement backtest page (/backtest)
    - Implement strategies page (/strategies)
    - Implement settings page (/settings)
    - Implement logout handler (/logout)
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9_
  
  - [ ]* 8.2 Write unit tests for UI routes
    - Test page rendering
    - Test session management
    - Test redirects
    - _Requirements: 9.8_

- [ ] 9. Checkpoint - Ensure all route tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Create integration tests
  - [ ] 10.1 Write API to business logic integration tests in tests/integration/test_api_integration.py
    - Test end-to-end API request flow through all layers
    - Test data persistence to database
    - Test state updates propagate correctly
    - _Requirements: 9.14_
  
  - [ ] 10.2 Write backtest integration tests in tests/integration/test_backtest_integration.py
    - Test full backtest execution with real data
    - Test progress callback integration
    - Test result persistence
    - _Requirements: 9.15_
  
  - [ ] 10.3 Write configuration integration tests in tests/integration/test_config_integration.py
    - Test configuration updates propagate to all components
    - Test preset application affects behavior
    - Test database and environment variable interaction
    - _Requirements: 9.16_
  
  - [ ]* 10.4 Write property test for module boundary enforcement
    - **Property 5: Module Boundary Enforcement**
    - **Validates: Requirements 1.8, 1.9**
    - Test that presentation layer never directly accesses data layer

- [ ] 11. Update main.py to use new modules
  - [ ] 11.1 Import new modules in main.py
    - Import api_bp from app.api.routes
    - Import ui_bp from app.ui.routes
    - Import get_app_state from app.core.state
    - Import service managers
    - _Requirements: 14.4_
  
  - [ ] 11.2 Initialize application state and services in main.py
    - Initialize ApplicationState singleton
    - Initialize ConfigService
    - Initialize TradingManager and BacktestManager
    - Set trader instance in ApplicationState
    - _Requirements: 14.4_
  
  - [ ] 11.3 Register new blueprints in main.py
    - Register api_bp with Flask app
    - Register ui_bp with Flask app
    - Keep dashboard.py routes as fallback
    - _Requirements: 14.4, 14.5_

- [ ] 12. Parallel system monitoring
  - [ ] 12.1 Add logging for new module usage
    - Log all API requests through new routes
    - Log all state updates
    - Log all configuration changes
    - _Requirements: 14.6_
  
  - [ ] 12.2 Verify backward compatibility
    - Test all existing API endpoints return same format
    - Test external integrations continue to work
    - Verify no breaking changes to API contracts
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

- [ ] 13. Checkpoint - Verify parallel systems working correctly
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Remove legacy code
  - [ ] 14.1 Remove dashboard.py after verification
    - Verify all functionality migrated to new modules
    - Remove dashboard.py file
    - Remove dashboard blueprint registration from main.py
    - _Requirements: 12.1, 14.7_
  
  - [ ] 14.2 Remove legacy strategy.py if unused
    - Verify strategy functionality in new structure
    - Remove legacy strategy.py file
    - _Requirements: 12.2, 14.8_
  
  - [ ] 14.3 Move tests to new structure
    - Organize all tests in tests/ directory
    - Remove old test files from root or other locations
    - _Requirements: 14.9_

- [ ] 15. Final cleanup and optimization
  - [ ] 15.1 Remove all deprecated code
    - Remove unused functions
    - Remove commented-out code
    - Remove temporary migration code
    - _Requirements: 12.3, 12.4, 12.5, 12.6, 14.10_
  
  - [ ] 15.2 Optimize imports
    - Remove unused imports
    - Organize imports according to PEP 8
    - _Requirements: 12.4, 14.10_
  
  - [ ] 15.3 Update documentation
    - Update README with new architecture
    - Document module structure
    - Update API documentation
    - _Requirements: 14.11_

- [ ] 16. Final checkpoint - Run complete test suite
  - Run all unit tests, integration tests, and property-based tests
  - Verify code coverage meets 80% minimum
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 9.9, 14.11_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation throughout the refactoring
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The phased approach ensures safe migration with rollback capability
- All existing API endpoints maintain backward compatibility
- New modules are created alongside existing code before migration
