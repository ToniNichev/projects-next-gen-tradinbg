/**
 * Timing History Module
 * Manages backtest timing history for progress estimation
 */

const BACKTEST_TIMING_KEY = 'backtest_timing_history';

export function getTimingHistory() {
  try {
    const stored = localStorage.getItem(BACKTEST_TIMING_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch (e) {
    console.error('Error reading timing history:', e);
    return {};
  }
}

export function saveTimingData(daysBack, duration) {
  try {
    const history = getTimingHistory();
    if (!history[daysBack]) {
      history[daysBack] = [];
    }
    history[daysBack].push(duration);
    
    // Keep only last 10 runs per days_back value
    if (history[daysBack].length > 10) {
      history[daysBack].shift();
    }
    
    localStorage.setItem(BACKTEST_TIMING_KEY, JSON.stringify(history));
  } catch (e) {
    console.error('Error saving timing data:', e);
  }
}

export function getEstimatedDuration(daysBack) {
  const history = getTimingHistory();
  const durations = history[daysBack];
  
  if (!durations || durations.length === 0) {
    // Default estimates based on days_back (1.5s per day as baseline)
    return daysBack * 1.5;
  }
  
  // Calculate average (like Jenkins does)
  return durations.reduce((a, b) => a + b) / durations.length;
}

// Days back selection persistence
const DAYS_BACK_KEY = 'backtest_days_back_selection';

export function saveDaysBackSelection(daysBack) {
  try {
    localStorage.setItem(DAYS_BACK_KEY, daysBack);
  } catch (e) {
    console.error('Error saving days_back selection:', e);
  }
}

export function restoreDaysBackSelection() {
  try {
    const saved = localStorage.getItem(DAYS_BACK_KEY);
    if (saved) {
      const dropdown = document.getElementById('days_back');
      const option = dropdown.querySelector(`option[value="${saved}"]`);
      if (option) {
        dropdown.value = saved;
      }
    }
  } catch (e) {
    console.error('Error restoring days_back selection:', e);
  }
}
