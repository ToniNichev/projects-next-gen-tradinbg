import threading
from datetime import datetime

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

_state = {
    "balances": {"USDT": 0.0, "BASE": 0.0},
    "last_signal": None,
    "last_trade": None,
    "updated_at": None,
}
_history = []
_max_history = 250

_ui_template = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Crypto Bot Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.min.js"></script>
    <style>
      body {
        font-family: system-ui, sans-serif;
        margin: 0;
        padding: 1rem;
        background: #0d1117;
        color: #e1e8ff;
      }
      main {
        max-width: 960px;
        margin: 0 auto;
      }
      .summary {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
        margin-bottom: 1rem;
      }
      .card {
        flex: 1;
        min-width: 200px;
        padding: 0.75rem 1rem;
        border-radius: 0.75rem;
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
      }
      canvas {
        width: 100% !important;
        height: 400px !important;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>Crypto Bot Chart</h1>
      <div class="summary">
        <div class="card">
          <p>Last signal</p>
          <h2 id="signal-text">--</h2>
          <p id="signal-detail"></p>
        </div>
        <div class="card">
          <p>Last trade</p>
          <h2 id="trade-text">--</h2>
          <p id="trade-detail"></p>
        </div>
      </div>
      <canvas id="priceChart"></canvas>
    </main>
    <script>
      const ctx = document.getElementById("priceChart").getContext("2d");
      const chart = new Chart(ctx, {
        type: "line",
        data: {
          datasets: [
            {
              label: "Price",
              borderColor: "#58D68D",
              backgroundColor: "rgba(88,214,141,0.2)",
              pointRadius: 0,
              data: [],
              yAxisID: "y",
            },
            {
              label: "Signals",
              type: "scatter",
              pointStyle: "triangle",
              pointRadius: 8,
              data: [],
              showLine: false,
            },
          ],
        },
        options: {
          animation: false,
          scales: {
            x: {
              type: "time",
              time: {
                tooltipFormat: "MMM dd HH:mm",
              },
              grid: {
                color: "rgba(255,255,255,0.08)",
              },
            },
            y: {
              grid: {
                color: "rgba(255,255,255,0.08)",
              },
            },
          },
        },
      });

      async function refresh() {
        const resp = await fetch("/history");
        const body = await resp.json();
        const history = body.history || [];
        chart.data.datasets[0].data = history.map((row) => ({
          x: row.timestamp,
          y: row.price,
        }));
        chart.data.datasets[1].data = history
          .filter((row) => row.signal_direction !== "neutral")
          .map((row) => ({
            x: row.timestamp,
            y: row.price,
            backgroundColor:
              row.signal_direction === "bullish" ? "#33ff8a" : "#ff5e57",
          }));
        chart.update();

        const lastSignal = history[history.length - 1];
        if (lastSignal) {
          document.getElementById("signal-text").textContent =
            lastSignal.signal_direction.toUpperCase();
          document.getElementById(
            "signal-detail"
          ).textContent = `${new Date(lastSignal.timestamp).toLocaleTimeString()} · price ${lastSignal.price.toFixed(
            2
          )}`;
        }
        const lastTrade = body.last_trade;
        if (lastTrade) {
          document.getElementById("trade-text").textContent =
            lastTrade.side.toUpperCase();
          document.getElementById(
            "trade-detail"
          ).textContent = `${lastTrade.timestamp} · ${lastTrade.usdt_balance.toFixed(
            2
          )} USDT`;
        }
      }

      refresh();
      setInterval(refresh, 5000);
    </script>
  </body>
</html>
"""


@app.route("/state")
def get_state():
    return jsonify(_state)


@app.route("/history")
def get_history():
    return jsonify(
        {"history": list(_history), "last_trade": _state.get("last_trade")}
    )


@app.route("/ui")
def get_ui():
    return render_template_string(_ui_template)


def _record_history(timestamp, price, signal_direction, trade_side):
    entry = {
        "timestamp": timestamp,
        "price": price,
        "signal_direction": signal_direction,
        "trade_side": trade_side,
    }
    _history.append(entry)
    if len(_history) > _max_history:
        _history.pop(0)


def update_state(
    balances=None,
    last_signal=None,
    last_trade=None,
    price=None,
    signal_direction=None,
    timestamp=None,
    trade_side=None,
    updated_at=None,
):
    if balances is not None:
        _state["balances"] = balances
    if last_signal is not None:
        _state["last_signal"] = last_signal
    if last_trade is not None:
        _state["last_trade"] = last_trade
    _state["updated_at"] = (
        updated_at or datetime.utcnow().isoformat()
    )
    if price is not None and signal_direction is not None:
        _record_history(
            timestamp or datetime.utcnow().isoformat(),
            price,
            signal_direction,
            trade_side,
        )


def start_dashboard(host="0.0.0.0", port=8000):
    def runner():
        app.run(host=host, port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()

