"""Settings each money pot really uses, for the Strategies page.

With pots on, each pot runs one strategy on its own money. Only the settings
listed here change what a pot does; the old page's on/off switches, weights,
voting and filters don't (they fed the single-account combined signal).

Values go to and from the page in display units: percents as 2.5 (not 0.025).
"""

from typing import Dict, List, Optional

from strategies.constants import StrategyNames

# key: saved setting name (strategy_configs table / BotConfig field)
# attr: the running strategy's attribute (None = read from BotConfig)
# pct: stored as a fraction, shown as a percent
FIELDS: Dict[str, dict] = {
    # RSI + Bollinger Bands (Intraday pot)
    "strategy_rsi_bb_rsi_oversold": dict(attr="rsi_oversold", label="Buy when RSI is below", kind="float",
        min=5, max=50, step=1, help="RSI under this means the price fell fast (oversold). Lower = waits for deeper drops, buys less often."),
    "strategy_rsi_bb_rsi_overbought": dict(attr="rsi_overbought", label="Sell signal when RSI is above", kind="float",
        min=50, max=95, step=1, help="RSI over this (at the upper band) turns the signal to sell."),
    "rsi_period": dict(attr="rsi_period", label="RSI length", kind="int", unit="candles",
        min=2, max=50, step=1, help="How many hourly candles RSI looks back over. 14 is the usual."),
    "strategy_rsi_bb_bb_period": dict(attr="bb_period", label="Band length", kind="int", unit="candles",
        min=5, max=100, step=1, help="The Bollinger middle line is the average of this many hourly closes."),
    "strategy_rsi_bb_bb_std_dev": dict(attr="bb_std_dev", label="Band width", kind="float", unit="× std dev",
        min=1, max=4, step=0.1, help="How far the bands sit from the middle line. Wider = the price has to fall further to buy."),
    "strategy_rsi_bb_take_profit_pct": dict(attr="take_profit_pct", label="Profit target, at most", kind="float", pct=True,
        min=0.5, max=20, step=0.1, help="Sells at the middle band or this much above the buy price, whichever comes first."),
    "use_atr_stops": dict(attr="use_atr_stops", label="Stop from recent price swings (ATR)", kind="bool",
        help="On: the stop sits a few 'average swings' (ATR) below the buy price. Off: a fixed percent below."),
    "atr_stop_multiplier": dict(attr="atr_stop_multiplier", label="Stop distance", kind="float", unit="× ATR",
        min=0.5, max=6, step=0.1, help="With ATR stops on: how many average swings below the buy price the stop goes."),
    "strategy_rsi_bb_stop_loss_pct": dict(attr="stop_loss_pct", label="Stop when ATR is off", kind="float", pct=True,
        min=0.5, max=15, step=0.1, help="Used only when 'Stop from recent price swings' is off."),
    "strategy_rsi_bb_require_both_signals": dict(attr="require_both_signals", label="Need RSI and the band together", kind="bool",
        help="On: buys only when RSI is low AND the price is at the lower band. Off: low RSI alone can be enough."),
    "strategy_rsi_bb_use_volume_filter": dict(attr="use_volume_filter", label="Prefer above-average volume", kind="bool",
        help="On: a signal on quiet trading counts for less."),
    # Trend Hold
    "strategy_trend_ma_days": dict(attr="ma_days", label="Average length", kind="int", unit="days",
        min=20, max=400, step=1, help="The daily close is compared with the average of this many days."),
    "strategy_trend_band": dict(attr="band", label="Band around the average", kind="float", pct=True,
        min=0, max=10, step=0.1, help="Buys when the daily close is this far above the average; sells when this far below. Wider = fewer, later trades."),
    "strategy_trend_emergency_stop_pct": dict(attr="emergency_stop_pct", label="Emergency stop", kind="float", pct=True,
        min=0, max=50, step=0.5, help="0 = none (the tested rule has none). Otherwise sells if the price falls this far below the buy price."),
    # Manual pot (BotConfig fields, read when you buy)
    "stop_loss_pct": dict(attr=None, label="Stop when ATR is off", kind="float", pct=True,
        min=0.5, max=15, step=0.1, help="Used only when 'Stop from recent price swings' is off."),
    "take_profit_pct": dict(attr=None, label="Profit target", kind="float", pct=True,
        min=0.5, max=30, step=0.1, help="Your buy gets a sell order at this much above the buy price."),
}

# Which settings each pot uses, in the order the page shows them
POT_FIELDS = {
    StrategyNames.RSI_BB_MEAN_REVERSION: [
        "strategy_rsi_bb_rsi_oversold", "strategy_rsi_bb_rsi_overbought", "rsi_period",
        "strategy_rsi_bb_bb_period", "strategy_rsi_bb_bb_std_dev", "strategy_rsi_bb_take_profit_pct",
        "use_atr_stops", "atr_stop_multiplier", "strategy_rsi_bb_stop_loss_pct",
        "strategy_rsi_bb_require_both_signals", "strategy_rsi_bb_use_volume_filter",
    ],
    StrategyNames.TREND_HOLD: [
        "strategy_trend_ma_days", "strategy_trend_band", "strategy_trend_emergency_stop_pct",
    ],
    "manual": ["take_profit_pct", "use_atr_stops", "atr_stop_multiplier", "stop_loss_pct"],
}

# Strategies no pot runs, and old controls that do nothing with pots
UNUSED_CONTROLS = [
    "The on/off switch for each strategy (a pot runs its strategy either way)",
    "Weights, voting mode and minimum confidence (they combined strategies into one signal)",
    "Signal filters (MACD / volume confirmation, trades per day)",
    "Position sizing (each pot uses its own buy size, shown on its card)",
    "Presets (turned off while pots are on: one click could change a live pot)",
]


def _key_of(pot) -> Optional[str]:
    if pot.strategy is None:
        return "manual" if pot.name == "manual" else None
    return pot.strategy.name if pot.strategy.name in POT_FIELDS else None


def _users(manager) -> Dict[str, List[str]]:
    """setting -> labels of the pots it changes (some are shared)."""
    out: Dict[str, List[str]] = {}
    for pot in manager.pots.values():
        for key in POT_FIELDS.get(_key_of(pot) or "", []):
            out.setdefault(key, []).append(pot.label)
    return out


def _live_value(key, pot, config):
    spec = FIELDS[key]
    raw = None
    if spec["attr"] and pot.strategy is not None and hasattr(pot.strategy, spec["attr"]):
        raw = getattr(pot.strategy, spec["attr"])
    elif spec["attr"] and hasattr(config, key):
        raw = getattr(config, key)  # shared setting, e.g. ATR for the Manual pot
    else:
        raw = getattr(config, key, None)
    return to_display(key, raw)


def to_display(key, raw):
    spec = FIELDS[key]
    if raw is None:
        return None
    if spec["kind"] == "bool":
        return bool(raw)
    if spec.get("pct"):
        return round(float(raw) * 100, 4)
    return int(raw) if spec["kind"] == "int" else round(float(raw), 4)


def from_display(key, value):
    """Check one value from the page; returns the stored value or raises ValueError."""
    spec = FIELDS[key]
    if spec["kind"] == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{spec['label']}: must be on or off")
        return value
    if isinstance(value, bool):
        raise ValueError(f"{spec['label']}: not a number")
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{spec['label']}: not a number")
    if num != num or not (spec["min"] <= num <= spec["max"]):
        raise ValueError(f"{spec['label']}: must be between {spec['min']} and {spec['max']}")
    if spec["kind"] == "int":
        if num != int(num):
            raise ValueError(f"{spec['label']}: must be a whole number")
        return int(num)
    return round(num / 100, 6) if spec.get("pct") else num


def _money(v):
    return f"${v:,.0f}"


def _rule(pot, config, price) -> dict:
    """How the pot decides, in plain words, plus what the numbers are right now."""
    s = pot.strategy
    sig = getattr(pot, "last_signal", None)
    ind = getattr(sig, "indicators", None) or {}
    info = getattr(sig, "info", None) or {}
    now: List[str] = []
    if s is None:
        stop = (f"{config.atr_stop_multiplier:g} × an estimated swing (2% of the price) below"
                if config.use_atr_stops else f"{config.stop_loss_pct * 100:g}% below")
        return {"rules": [
            "You decide when to buy and sell (Manual Trading on the dashboard). The bot never trades this pot.",
            f"Each buy gets a stop {stop} the buy price, waiting on Binance.US, and a profit target "
            f"{config.take_profit_pct * 100:g}% above it.",
        ], "now": now}
    if s.name == StrategyNames.TREND_HOLD:
        band = f"{s.band * 100:g}%"
        rules = [
            f"Once a day, compares BTC's daily close with its {s.ma_days}-day average.",
            f"Buys (uses {getattr(s, 'position_size', 0.99) * 100:g}% of its cash) when the close is more than {band} above the average.",
            f"Sells everything when the close is more than {band} below it. In between, it keeps what it has.",
            ("No stop: it rides out dips and exits only on its rule (the tested rule has none)."
             if not s.emergency_stop_pct else
             f"Emergency stop {s.emergency_stop_pct * 100:g}% below the buy price."),
        ]
        avg = next((v for k, v in ind.items() if str(k).startswith("sma_")), None) or info.get("ma")
        if avg:
            now.append(f"{s.ma_days}-day average {_money(avg)}: buys above {_money(avg * (1 + s.band))}, "
                       f"sells below {_money(avg * (1 - s.band))}")
        return {"rules": rules, "now": now}
    if s.name == StrategyNames.RSI_BB_MEAN_REVERSION:
        stop = (f"{s.atr_stop_multiplier:g} × ATR (the average hourly swing) below the buy price"
                if s.use_atr_stops else f"{s.stop_loss_pct * 100:g}% below the buy price")
        both = "and" if s.require_both_signals else "(ideally also)"
        rules = [
            f"Every hour, looks for a sharp drop: RSI below {s.rsi_oversold:g} {both} the price at or under "
            f"the lower Bollinger band ({s.bb_period} hours, {s.bb_std_dev:g}× wide).",
            (f"Then buys with {pot.order_pct * 100:g}% of its cash" if pot.order_pct
             else "Then buys (the size depends on how strong the signal is)")
            + (f", at most {pot.max_buys_per_day} buys a day." if pot.max_buys_per_day else "."),
            f"Sells at the middle band or +{s.take_profit_pct * 100:g}%, whichever comes first; "
            f"at its stop ({stop}); or when RSI goes above {s.rsi_overbought:g} at the upper band.",
        ]
        if ind.get("rsi") is not None:
            now.append(f"RSI {float(ind['rsi']):.1f} (buys below {s.rsi_oversold:g})")
        if ind.get("bb_lower"):
            now.append(f"lower band {_money(float(ind['bb_lower']))} · middle {_money(float(ind.get('bb_middle') or 0))}"
                       + (f" · price {_money(price)}" if price else ""))
        return {"rules": rules, "now": now}
    return {"rules": [f"Runs {s.name}."], "now": now}


def describe(manager, config, price=None) -> dict:
    users = _users(manager)
    pots = []
    for pot in manager.pots.values():
        key = _key_of(pot)
        style = manager.pot_style(pot.name) if hasattr(manager, "pot_style") else {}
        fields = []
        for k in POT_FIELDS.get(key or "", []):
            spec = FIELDS[k]
            others = [u for u in users.get(k, []) if u != pot.label]
            fields.append({
                "key": k, "label": spec["label"], "kind": spec["kind"], "pct": bool(spec.get("pct")),
                "unit": "%" if spec.get("pct") else spec.get("unit", ""),
                "min": spec.get("min"), "max": spec.get("max"), "step": spec.get("step"),
                "help": spec["help"], "value": _live_value(k, pot, config), "also": others,
            })
        trader = pot.trader
        pots.append({
            "name": pot.name, "label": pot.label,
            "color": style.get("color"), "letter": style.get("letter"),
            "strategy": pot.strategy.name if pot.strategy else None,
            "holding": bool(trader and getattr(trader, "open_position", None)),
            "paused": bool(getattr(pot, "paused", False)),
            "editable": key is not None,
            "settings": fields,
            **_rule(pot, config, price),
        })
    used = {p.strategy.name for p in manager.pots.values() if p.strategy}
    return {"pots": pots, "unused_controls": UNUSED_CONTROLS,
            "unused_strategies": [StrategyNames.get_display_name(n) for n in StrategyNames.all_names()
                                  if n not in used]}


def plan_changes(manager, config, pot_name, changes) -> List[dict]:
    """Check a change request. Returns [{key, label, before, after, stored, also}]; raises ValueError."""
    pot = manager.pots.get(pot_name)
    if pot is None:
        raise ValueError("unknown pot")
    allowed = POT_FIELDS.get(_key_of(pot) or "", [])
    if not isinstance(changes, dict) or not changes:
        raise ValueError("nothing to change")
    users = _users(manager)
    out = []
    for k, v in changes.items():
        if k not in allowed:
            raise ValueError(f"{pot.label} doesn't use the setting '{k}'")
        stored = from_display(k, v)
        before = _live_value(k, pot, config)
        after = to_display(k, stored)
        if before == after:
            continue
        out.append({"key": k, "label": FIELDS[k]["label"], "before": before, "after": after,
                    "stored": stored, "unit": "%" if FIELDS[k].get("pct") else FIELDS[k].get("unit", ""),
                    "also": [u for u in users.get(k, []) if u != pot.label]})
    if not out:
        raise ValueError("no setting changed")
    return out


LIVE_KEYS = set(FIELDS)
