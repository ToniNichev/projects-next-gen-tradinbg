"""
Property-based test for state consistency.

**Validates: Requirements 2.2, 2.3, 2.4, 8.10, 8.11**

This module tests the universal property that concurrent state updates
maintain consistency across all threads with no race conditions.

Property: Thread-safe state updates
∀ thread₁, thread₂ ∈ Threads:
  concurrent updates ⟹ final_state is consistent (no race conditions)
"""

import pytest
import threading
from app.core.state import ApplicationState, get_app_state


class TestStateConsistency:
    """Property tests for state consistency under concurrent access."""
    
    def test_concurrent_balance_updates_no_race_conditions(self):
        """
        Test that concurrent balance updates maintain consistency.
        
        **Validates: Requirements 2.2, 2.3, 2.4, 8.10, 8.11**
        
        This test spawns multiple threads that concurrently update the USDT balance.
        Each thread increments the balance by a fixed amount multiple times.
        The final balance should be exactly the sum of all increments with no lost updates.
        """
        # Create a fresh ApplicationState instance for this test
        app_state = ApplicationState()
        
        # Initialize balance to 0
        app_state.update_trading_state(usdt_balance=0.0)
        
        # Configuration
        num_threads = 5
        increments_per_thread = 100
        increment_amount = 1.0
        
        # Expected final balance
        expected_balance = num_threads * increments_per_thread * increment_amount
        
        def update_balance(amount: float, iterations: int):
            """Worker function that updates balance multiple times."""
            for _ in range(iterations):
                # Read current state
                state = app_state.get_trading_state()
                # Update with incremented value
                app_state.update_trading_state(usdt_balance=state.usdt_balance + amount)
        
        # Create and start threads
        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(
                target=update_balance,
                args=(increment_amount, increments_per_thread)
            )
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify final balance is exactly correct (no lost updates)
        final_state = app_state.get_trading_state()
        assert final_state.usdt_balance == expected_balance, (
            f"Expected balance {expected_balance}, got {final_state.usdt_balance}. "
            f"Lost updates detected!"
        )
    
    def test_concurrent_mixed_field_updates_maintain_consistency(self):
        """
        Test that concurrent updates to different fields maintain consistency.
        
        **Validates: Requirements 2.2, 2.3, 2.4, 8.10, 8.11**
        
        This test spawns threads that update different fields concurrently.
        All updates should be applied atomically with no partial state.
        """
        app_state = ApplicationState()
        
        # Initialize state
        app_state.update_trading_state(
            usdt_balance=1000.0,
            base_balance=0.5,
            current_price=50000.0,
            trading_enabled=False
        )
        
        num_iterations = 50
        
        def update_usdt_balance():
            """Update USDT balance."""
            for _ in range(num_iterations):
                state = app_state.get_trading_state()
                app_state.update_trading_state(usdt_balance=state.usdt_balance + 10.0)
        
        def update_base_balance():
            """Update base balance."""
            for _ in range(num_iterations):
                state = app_state.get_trading_state()
                app_state.update_trading_state(base_balance=state.base_balance + 0.01)
        
        def update_price():
            """Update current price."""
            for _ in range(num_iterations):
                state = app_state.get_trading_state()
                app_state.update_trading_state(current_price=state.current_price + 100.0)
        
        def toggle_trading():
            """Toggle trading enabled flag."""
            for _ in range(num_iterations):
                state = app_state.get_trading_state()
                app_state.update_trading_state(trading_enabled=not state.trading_enabled)
        
        # Create threads for different field updates
        threads = [
            threading.Thread(target=update_usdt_balance),
            threading.Thread(target=update_base_balance),
            threading.Thread(target=update_price),
            threading.Thread(target=toggle_trading),
        ]
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify expected final values
        final_state = app_state.get_trading_state()
        
        expected_usdt = 1000.0 + (num_iterations * 10.0)
        expected_base = 0.5 + (num_iterations * 0.01)
        expected_price = 50000.0 + (num_iterations * 100.0)
        
        assert final_state.usdt_balance == expected_usdt, (
            f"USDT balance mismatch: expected {expected_usdt}, got {final_state.usdt_balance}"
        )
        assert abs(final_state.base_balance - expected_base) < 0.0001, (
            f"Base balance mismatch: expected {expected_base}, got {final_state.base_balance}"
        )
        assert final_state.current_price == expected_price, (
            f"Price mismatch: expected {expected_price}, got {final_state.current_price}"
        )
    
    def test_concurrent_atomic_updates_no_partial_state(self):
        """
        Test that multi-field updates are atomic (all-or-nothing).
        
        **Validates: Requirements 2.3, 2.4, 8.10, 8.11**
        
        This test verifies that when multiple fields are updated together,
        either all fields are updated or none are (atomic operation).
        """
        app_state = ApplicationState()
        
        # Initialize state
        app_state.update_trading_state(
            usdt_balance=1000.0,
            base_balance=1.0,
            position_open=False
        )
        
        num_threads = 10
        updates_per_thread = 50
        
        def atomic_update(thread_id: int):
            """Perform atomic multi-field updates."""
            for i in range(updates_per_thread):
                state = app_state.get_trading_state()
                # Update multiple fields atomically
                app_state.update_trading_state(
                    usdt_balance=state.usdt_balance + 1.0,
                    base_balance=state.base_balance + 0.001
                )
        
        # Create and run threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=atomic_update, args=(i,))
            threads.append(thread)
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify both fields updated correctly
        final_state = app_state.get_trading_state()
        
        expected_usdt = 1000.0 + (num_threads * updates_per_thread * 1.0)
        expected_base = 1.0 + (num_threads * updates_per_thread * 0.001)
        
        assert final_state.usdt_balance == expected_usdt, (
            f"USDT balance incorrect: expected {expected_usdt}, got {final_state.usdt_balance}"
        )
        assert abs(final_state.base_balance - expected_base) < 0.0001, (
            f"Base balance incorrect: expected {expected_base}, got {final_state.base_balance}"
        )
    
    def test_singleton_consistency_across_threads(self):
        """
        Test that get_app_state() returns the same instance across threads.
        
        **Validates: Requirements 2.5, 2.6**
        
        This test verifies the singleton pattern works correctly under
        concurrent access from multiple threads.
        """
        instances = []
        lock = threading.Lock()
        
        def get_instance():
            """Get app state instance from thread."""
            instance = get_app_state()
            with lock:
                instances.append(id(instance))
        
        # Create multiple threads that get the app state
        threads = []
        for _ in range(20):
            thread = threading.Thread(target=get_instance)
            threads.append(thread)
        
        # Start all threads simultaneously
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify all threads got the same instance
        assert len(set(instances)) == 1, (
            f"Multiple ApplicationState instances detected: {len(set(instances))} unique instances"
        )
    
    def test_concurrent_history_updates_maintain_order(self):
        """
        Test that concurrent history record additions maintain consistency.
        
        **Validates: Requirements 2.2, 8.10, 8.11, 16.1, 16.5**
        
        This test verifies that history records are added safely from
        multiple threads without data corruption.
        """
        app_state = ApplicationState()
        
        # Clear any existing history
        app_state.clear_history()
        
        num_threads = 5
        records_per_thread = 20
        
        def add_history_records(thread_id: int):
            """Add history records from a thread."""
            for i in range(records_per_thread):
                record = {
                    'thread_id': thread_id,
                    'record_num': i,
                    'action': f'action_{thread_id}_{i}'
                }
                app_state.add_history_record(record)
        
        # Create and run threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=add_history_records, args=(i,))
            threads.append(thread)
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify total number of records
        history = app_state.get_history(limit=1000)
        expected_total = num_threads * records_per_thread
        
        assert len(history) == expected_total, (
            f"Expected {expected_total} history records, got {len(history)}"
        )
        
        # Verify all records have required fields
        for record in history:
            assert 'thread_id' in record
            assert 'record_num' in record
            assert 'action' in record
            assert 'timestamp' in record  # Should be auto-added
    
    def test_concurrent_backtest_result_additions(self):
        """
        Test that concurrent backtest result additions maintain consistency.
        
        **Validates: Requirements 2.2, 8.10, 8.11, 18.8**
        
        This test verifies that backtest results can be added safely from
        multiple threads without data corruption.
        """
        app_state = ApplicationState()
        
        # Clear any existing results
        app_state.clear_backtest_results()
        
        num_threads = 5
        results_per_thread = 10
        
        def add_backtest_results(thread_id: int):
            """Add backtest results from a thread."""
            for i in range(results_per_thread):
                result = {
                    'id': f'backtest_{thread_id}_{i}',
                    'thread_id': thread_id,
                    'result_num': i,
                    'total_trades': i * 10,
                    'pnl_pct': i * 0.5
                }
                app_state.add_backtest_result(result)
        
        # Create and run threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=add_backtest_results, args=(i,))
            threads.append(thread)
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify total number of results
        results = app_state.get_backtest_results()
        expected_total = num_threads * results_per_thread
        
        assert len(results) == expected_total, (
            f"Expected {expected_total} backtest results, got {len(results)}"
        )
        
        # Verify all results have required fields
        for result in results:
            assert 'id' in result
            assert 'thread_id' in result
            assert 'result_num' in result
