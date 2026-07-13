/**
 * Backtest Runner Module
 * Handles backtest execution, progress tracking, and status polling.
 */

import { getEstimatedDuration, saveTimingData } from './timing.js';
import { populateProgressInfo, loadCurrentStrategyConfig } from './strategy-config.js';

let activeAbortController = null;

const POLL_INTERVAL_MS = 1000;
const MAX_POLL_ATTEMPTS = 1800;

function formatElapsed(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function getElements() {
  return {
    btn: document.getElementById('run-current-btn'),
    cancelBtn: document.getElementById('cancel-backtest-btn'),
    text: document.getElementById('run-current-text'),
    status: document.getElementById('backtest-status'),
    progressDiv: document.getElementById('backtest-progress'),
    progressBar: document.getElementById('progress-bar'),
    progressTime: document.getElementById('progress-time'),
    progressPercent: document.getElementById('progress-percent'),
    progressStatus: document.getElementById('progress-status'),
  };
}

function setRunningState(els, running) {
  els.btn.disabled = running;
  els.btn.classList.toggle('btn-running', running);
  if (els.cancelBtn) els.cancelBtn.style.display = running ? '' : 'none';
  if (!running) {
    els.text.textContent = '🚀 Run Backtest';
    loadCurrentStrategyConfig();
  }
}

function updateProgressBar(els, pct, statusText, timeText) {
  els.progressBar.style.width = `${Math.min(pct, 100)}%`;
  els.progressPercent.textContent = `${Math.round(pct)}%`;
  if (statusText) els.progressStatus.textContent = statusText;
  if (timeText) els.progressTime.textContent = timeText;
}

const PHASE_MESSAGES = [
  [10, 'Fetching historical data...'],
  [30, 'Calculating indicators...'],
  [60, 'Running strategy signals...'],
  [90, 'Simulating trades...'],
  [100, 'Finalizing results...'],
];

function getPhaseMessage(pct) {
  for (const [threshold, msg] of PHASE_MESSAGES) {
    if (pct < threshold) return msg;
  }
  return 'Finalizing results...';
}

export async function runQuickBacktest() {
  if (activeAbortController) {
    activeAbortController.abort();
  }
  activeAbortController = new AbortController();
  const { signal } = activeAbortController;

  const els = getElements();
  const daysBack = parseInt(document.getElementById('days_back').value);
  const skipLlm = document.getElementById('skip_llm')?.checked ?? true;
  const endDate = document.getElementById('end_date')?.value || null;

  let configOverrides = null;
  if (document.getElementById('override_strategies')?.checked) {
    configOverrides = {
      strategy_ema_enabled: document.getElementById('override_ema').checked,
      strategy_rsi_bb_enabled: document.getElementById('override_rsi_bb').checked,
      strategy_macd_enabled: document.getElementById('override_macd').checked,
    };
  }

  const estimatedDuration = getEstimatedDuration(daysBack);
  const startTime = Date.now();

  setRunningState(els, true);
  els.text.textContent = '⏳ Running...';
  els.progressDiv.style.display = 'block';
  els.status.innerHTML = '';

  await populateProgressInfo(daysBack, endDate);

  updateProgressBar(els, 0, 'Initializing backtest...', `~${Math.round(estimatedDuration)}s estimated`);

  let useEstimatedProgress = true;
  const progressInterval = setInterval(() => {
    if (!useEstimatedProgress) return;
    const elapsed = (Date.now() - startTime) / 1000;
    const pct = Math.min((elapsed / estimatedDuration) * 100, 95);
    const remaining = Math.max(estimatedDuration - elapsed, 0);
    const elapsedStr = formatElapsed(elapsed);

    updateProgressBar(
      els,
      pct,
      getPhaseMessage(pct),
      `${elapsedStr} elapsed · ~${Math.round(remaining)}s remaining`
    );
  }, 200);

  try {
    const response = await fetch('/api/backtest/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        days_back: daysBack,
        skip_llm: skipLlm,
        end_date: endDate,
        config_overrides: configOverrides,
      }),
      signal,
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.error || `Server responded with ${response.status}`);
    }

    const data = await response.json();
    sessionStorage.setItem('activeBacktestId', data.backtest_id);
    sessionStorage.setItem('activeBacktestStart', String(startTime));
    sessionStorage.setItem('activeBacktestDays', String(daysBack));
    pollBacktestStatus(data.backtest_id, progressInterval, startTime, daysBack, signal, useEstimatedProgress, (val) => { useEstimatedProgress = val; });
  } catch (error) {
    clearInterval(progressInterval);
    if (error.name === 'AbortError') return;
    els.status.innerHTML = `<p class="text-danger">Error: ${error.message}</p>`;
    els.progressDiv.style.display = 'none';
    setRunningState(els, false);
  }
}

function pollBacktestStatus(backtestId, progressInterval, startTime, daysBack, signal, useEstimatedProgress, setUseEstimated) {
  let attempts = 0;
  const els = getElements();

  const interval = setInterval(async () => {
    if (signal.aborted) {
      clearInterval(interval);
      clearInterval(progressInterval);
      return;
    }

    attempts++;

    try {
      const [resultsResponse, statusResponse] = await Promise.all([
        fetch('/api/backtest/results', { signal }),
        fetch('/api/backtest/status', { signal }),
      ]);

      const resultsData = await resultsResponse.json();
      const statusData = await statusResponse.json();
      const results = resultsData.data?.results || resultsData.results || [];
      const result = backtestId
        ? results.find(r => r.id === backtestId)
        : results.find(r => r.status === 'completed');
      const currentStatus = statusData.data || statusData;
      const elapsed = (Date.now() - startTime) / 1000;
      const elapsedStr = formatElapsed(elapsed);

      if (currentStatus.running && currentStatus.progress) {
        const progress = currentStatus.progress;
        if (progress.total_analyses > 0) {
          setUseEstimated(false);
          clearInterval(progressInterval);

          const pct = (progress.completed_analyses / progress.total_analyses) * 100;
          let timeStr = `${elapsedStr} elapsed · Analysis ${progress.completed_analyses}/${progress.total_analyses}`;
          if (progress.eta_seconds > 0) {
            timeStr += ` · ~${Math.ceil(progress.eta_seconds / 60)} min remaining`;
          }

          updateProgressBar(
            els,
            Math.min(pct, 95),
            `Processing candle ${progress.current_candle}/${progress.total_candles}...`,
            timeStr
          );
        }
      }

      if (result && result.status === 'completed') {
        clearInterval(interval);
        clearInterval(progressInterval);

        const actualDuration = (Date.now() - startTime) / 1000;
        saveTimingData(daysBack, actualDuration);

        sessionStorage.removeItem('activeBacktestId');
        sessionStorage.removeItem('activeBacktestStart');
        sessionStorage.removeItem('activeBacktestDays');
        updateProgressBar(els, 100, '✓ Backtest completed successfully!', 'Complete!');
        els.progressTime.style.color = 'var(--accent-green)';
        els.progressStatus.style.color = 'var(--accent-green)';
        els.status.innerHTML = `<p class="text-success">✓ Completed in ${actualDuration.toFixed(1)}s</p>`;

        setTimeout(() => {
          els.progressDiv.style.display = 'none';
          els.progressTime.style.color = '';
          els.progressStatus.style.color = '';
          els.status.innerHTML = '';
          setRunningState(els, false);
        }, 3000);

        if (window.BacktestResults?.loadResults) {
          window.BacktestResults.loadResults();
        }
      } else if (result && result.status === 'failed') {
        clearInterval(interval);
        clearInterval(progressInterval);
        els.status.innerHTML = `<p class="text-danger">✗ Backtest failed: ${result.error || 'Unknown error'}</p>`;
        els.progressDiv.style.display = 'none';
        setRunningState(els, false);
      } else if (attempts >= MAX_POLL_ATTEMPTS) {
        clearInterval(interval);
        clearInterval(progressInterval);
        els.status.innerHTML = '<p class="text-danger">Timeout waiting for results</p>';
        els.progressDiv.style.display = 'none';
        setRunningState(els, false);
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        clearInterval(interval);
        clearInterval(progressInterval);
        return;
      }
      console.error('Error polling status:', error);
    }
  }, POLL_INTERVAL_MS);
}

export async function cancelBacktest() {
  const els = getElements();
  if (els.cancelBtn) {
    els.cancelBtn.disabled = true;
    els.cancelBtn.textContent = 'Cancelling...';
  }
  if (activeAbortController) activeAbortController.abort();
  try {
    const resp = await fetch('/api/backtest/cancel', { method: 'POST' });
    const data = await resp.json();
    if (data.success) {
      els.progressStatus.textContent = 'Cancelling — waiting for current analysis to finish...';
      // Poll until server confirms running=false (current LLM call must complete first)
      const pollCancel = setInterval(async () => {
        try {
          const sr = await fetch('/api/backtest/status');
          const sd = await sr.json();
          const st = sd.data || sd;
          if (!st.running) {
            clearInterval(pollCancel);
            sessionStorage.removeItem('activeBacktestId');
      sessionStorage.removeItem('activeBacktestStart');
      sessionStorage.removeItem('activeBacktestDays');
      els.status.innerHTML = '<p class="text-warning">Backtest cancelled.</p>';
            els.progressDiv.style.display = 'none';
            setRunningState(els, false);
          }
        } catch (_) {}
      }, 1000);
    }
  } catch (e) {
    console.error('Cancel failed:', e);
    if (els.cancelBtn) {
      els.cancelBtn.disabled = false;
      els.cancelBtn.textContent = '✕ Cancel';
    }
  }
}

export async function resumeIfRunning() {
  const backtestId = sessionStorage.getItem('activeBacktestId');
  const startTimeStr = sessionStorage.getItem('activeBacktestStart');
  const daysBack = parseInt(sessionStorage.getItem('activeBacktestDays') || '30');

  try {
    const resp = await fetch('/api/backtest/status');
    const data = await resp.json();
    const status = data.data || data;
    if (!status.running) return;
  } catch (_) { return; }

  // Backtest is running — restore the UI
  const els = getElements();
  // Prefer server-reported start time — accurate even across tabs/sessions
  let startTime = startTimeStr ? parseInt(startTimeStr) : Date.now();
  try {
    const sr = await fetch('/api/backtest/status');
    const sd = await sr.json();
    const st = sd.data || sd;
    if (st.started_at_ms) startTime = st.started_at_ms;
  } catch (_) {}

  setRunningState(els, true);
  els.progressDiv.style.display = 'block';
  els.status.innerHTML = '';
  updateProgressBar(els, 0, 'Backtest in progress...', 'Resuming...');

  if (activeAbortController) activeAbortController.abort();
  activeAbortController = new AbortController();
  const { signal } = activeAbortController;

  let useEstimatedProgress = !backtestId;
  const progressInterval = null; // no estimated progress on resume

  pollBacktestStatus(
    backtestId || '',
    progressInterval,
    startTime,
    daysBack,
    signal,
    useEstimatedProgress,
    (val) => { useEstimatedProgress = val; }
  );
}
