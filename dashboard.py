import logging as flask_logging
import os
import threading
from datetime import datetime

from flask import Flask, jsonify, render_template

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))

# Reduce Flask logging noise - only show errors
log = flask_logging.getLogger('werkzeug')
log.setLevel(flask_logging.ERROR)

_state = {
    "balances": {"USDT": 0.0, "BASE": 0.0},
    "last_signal": None,
    "last_trade": None,
    "updated_at": None,
}
_history = []
_max_history = 250


@app.route("/state")
def get_state():
    return jsonify(_state)


@app.route("/history")
def get_history():
    return jsonify(
        {
            "history": list(_history),
            "last_signal": _state.get("last_signal"),
            "last_trade": _state.get("last_trade"),
        }
    )


@app.route("/ui")
def get_ui():
    return render_template("ui.html")


def _record_history(timestamp, price, signal_direction, trade_side, ohlc=None):
    candle = {
        "open": price,
        "high": price,
        "low": price,
        "close": price,
    }
    if ohlc:
        candle.update(ohlc)
    entry = {
        "timestamp": timestamp,
        "price": candle["close"],
        "signal_direction": signal_direction,
        "trade_side": trade_side,
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
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
    ohlc=None,
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
            ohlc=ohlc,
        )


def start_dashboard(host="0.0.0.0", port=8000):
    def runner():
        app.run(host=host, port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()

