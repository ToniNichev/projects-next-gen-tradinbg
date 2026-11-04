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
    # Shared by the Manual pot (read when you buy) and EMA Crossover
    "stop_loss_pct": dict(attr="stop_loss_pct", label="Stop when ATR is off", kind="float", pct=True,
        min=0.5, max=15, step=0.1, help="Used only when 'Stop from recent price swings' is off."),
    "take_profit_pct": dict(attr="take_profit_pct", label="Profit target", kind="float", pct=True,
        min=0.5, max=30, step=0.1, help="Sells when the price gets this much above the buy price."),
    # EMA Crossover
    "short_window": dict(attr="short_window", label="Fast average", kind="int", unit="candles",
        min=2, max=100, step=1, help="Length of the quick-moving average (hourly candles)."),
    "long_window": dict(attr="long_window", label="Slow average", kind="int", unit="candles",
        min=5, max=300, step=1, help="Length of the slow average. A buy is the fast one crossing above it. Must be longer than the fast one."),
    "rsi_oversold": dict(attr="rsi_oversold", label="Skip a cross when RSI is below", kind="float",
        min=5, max=50, step=1, help="A cross while RSI is this low (a crash) is ignored."),
    "rsi_overbought": dict(attr="rsi_overbought", label="Skip a cross when RSI is above", kind="float",
        min=50, max=95, step=1, help="A cross while RSI is this high (already stretched) is ignored."),
    "require_volume_confirmation": dict(attr="require_volume_confirmation", label="Need above-average volume", kind="bool",
        help="On: a cross on quiet trading is ignored (EMA) or counts for less (MACD)."),
    "require_macd_confirmation": dict(attr="require_macd_confirmation", label="Need MACD to agree", kind="bool",
        help="On: buys only when MACD also points up."),
    # MACD + Volume
    "strategy_macd_fast_period": dict(attr="macd_fast_period", label="MACD fast length", kind="int", unit="candles",
        min=2, max=50, step=1, help="The usual is 12. Must be shorter than the slow length."),
    "strategy_macd_slow_period": dict(attr="macd_slow_period", label="MACD slow length", kind="int", unit="candles",
        min=5, max=100, step=1, help="The usual is 26."),
    "strategy_macd_signal_period": dict(attr="macd_signal_period", label="Signal line length", kind="int", unit="candles",
        min=2, max=30, step=1, help="The usual is 9. A buy is MACD crossing above this line."),
    "strategy_macd_volume_multiplier": dict(attr="volume_multiplier", label="Strong volume means", kind="float", unit="× average",
        min=0.5, max=5, step=0.1, help="Volume at least this many times the 20-hour average strengthens a signal."),
    "strategy_macd_require_zero_cross": dict(attr="require_zero_cross", label="Buy only above the zero line", kind="bool",
        help="On: MACD must also be above zero (an uptrend already under way)."),
    "strategy_macd_use_momentum_filter": dict(attr="use_momentum_filter", label="Use the momentum check", kind="bool",
        help="On: a signal without price momentum counts for less."),
    "strategy_macd_take_profit_pct": dict(attr="take_profit_pct", label="Profit target", kind="float", pct=True,
        min=0.5, max=30, step=0.1, help="Sells when the price gets this much above the buy price."),
    "strategy_macd_stop_loss_pct": dict(attr="stop_loss_pct", label="Stop when ATR is off", kind="float", pct=True,
        min=0.5, max=15, step=0.1, help="Used only when 'Stop from recent price swings' is off."),
}

# Where a strategy keeps a shared setting under another name
ATTR_OVERRIDES = {
    (StrategyNames.MACD_VOLUME_MOMENTUM, "require_volume_confirmation"): "use_volume_filter",
}

# Pairs that must stay in order (smaller, larger)
ORDERED_PAIRS = [
    ("short_window", "long_window"),
    ("strategy_macd_fast_period", "strategy_macd_slow_period"),
    ("rsi_oversold", "rsi_overbought"),
    ("strategy_rsi_bb_rsi_oversold", "strategy_rsi_bb_rsi_overbought"),
]

# Backtest switches: run only this strategy (the backtest otherwise combines them)
ENABLE_KEYS = {
    StrategyNames.TREND_HOLD: "strategy_trend_enabled",
    StrategyNames.RSI_BB_MEAN_REVERSION: "strategy_rsi_bb_enabled",
    StrategyNames.EMA_CROSSOVER: "strategy_ema_enabled",
    StrategyNames.MACD_VOLUME_MOMENTUM: "strategy_macd_enabled",
}

# One line per strategy for the "Add a pot" form
CHOICE_BLURBS = {
    "trend_hold": "Holds BTC while it's above its 100-day average, cash below. A few trades a year.",
    "rsi_bb": "Buys sharp hourly drops (low RSI at the lower band), sells the bounce. Can trade several times a week.",
    "ema_crossover": "Buys when a fast hourly average crosses above a slow one; sells on the cross back down.",
    "macd_volume": "Buys when MACD crosses up with momentum and volume behind it; sells when it turns down.",
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
    StrategyNames.EMA_CROSSOVER: [
        "short_window", "long_window", "rsi_oversold", "rsi_overbought", "rsi_period",
        "take_profit_pct", "use_atr_stops", "atr_stop_multiplier", "stop_loss_pct",
        "require_volume_confirmation", "require_macd_confirmation",
    ],
    StrategyNames.MACD_VOLUME_MOMENTUM: [
        "strategy_macd_fast_period", "strategy_macd_slow_period", "strategy_macd_signal_period",
        "strategy_macd_volume_multiplier", "require_volume_confirmation",
        "strategy_macd_require_zero_cross", "strategy_macd_use_momentum_filter",
        "strategy_macd_take_profit_pct", "use_atr_stops", "atr_stop_multiplier", "strategy_macd_stop_loss_pct",
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
    """What the running pot uses: its strategy's attribute, or (Manual pot)
    the saved setting it reads when you buy."""
    s = pot.strategy
    attr = ATTR_OVERRIDES.get((s.name, key), FIELDS[key]["attr"]) if s is not None else None
    if attr and hasattr(s, attr):
        raw = getattr(s, attr)
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
    stop = (f"{s.atr_stop_multiplier:g} × ATR (the average hourly swing) below the buy price"
            if getattr(s, "use_atr_stops", False) else f"{getattr(s, 'stop_loss_pct', 0) * 100:g}% below the buy price")
    size = ((f"Buys with {pot.order_pct * 100:g}% of its cash" if pot.order_pct
             else "Buys (the size depends on how strong the signal is)")
            + (f", at most {pot.max_buys_per_day} buys a day." if pot.max_buys_per_day else "."))
    if s.name == StrategyNames.EMA_CROSSOVER:
        rules = [
            f"Every hour, checks whether the {s.short_window}-hour average just crossed above the "
            f"{s.long_window}-hour average (a turn up).",
            f"Ignores the cross when RSI is below {s.rsi_oversold:g} or above {s.rsi_overbought:g}"
            + (", on below-average volume" if s.require_volume_confirmation else "")
            + (", or when MACD disagrees" if s.require_macd_confirmation else "") + ".",
            size,
            f"Sells at +{s.take_profit_pct * 100:g}%, at its stop ({stop}), or when the fast average crosses back below.",
        ]
        if ind.get("short_ema") and ind.get("long_ema"):
            gap = float(ind["short_ema"]) / float(ind["long_ema"]) - 1
            now.append(f"fast average {_money(float(ind['short_ema']))} is {abs(gap) * 100:.2f}% "
                       f"{'above' if gap >= 0 else 'below'} the slow one {_money(float(ind['long_ema']))}")
        if ind.get("rsi") is not None:
            now.append(f"RSI {float(ind['rsi']):.1f}")
        return {"rules": rules, "now": now}
    if s.name == StrategyNames.MACD_VOLUME_MOMENTUM:
        rules = [
            f"Every hour, checks whether MACD ({s.macd_fast_period}/{s.macd_slow_period}) just crossed above "
            f"its {s.macd_signal_period}-hour signal line with the gap widening"
            + (" and MACD above zero" if s.require_zero_cross else "") + ".",
            "Stronger with volume at least "
            f"{s.volume_multiplier:g}× the average" + (" and price momentum" if s.use_momentum_filter else "")
            + "; weak signals are skipped.",
            size,
            f"Sells at +{s.take_profit_pct * 100:g}%, at its stop ({stop}), or when MACD crosses back down.",
        ]
        macd = ind.get("macd_line", ind.get("macd"))
        sigl = ind.get("signal_line", ind.get("macd_signal"))
        if macd is not None and sigl is not None:
            now.append(f"MACD {float(macd):,.1f} is {'above' if float(macd) >= float(sigl) else 'below'} "
                       f"its signal line {float(sigl):,.1f}")
        if ind.get("volume_ratio") is not None:
            now.append(f"volume {float(ind['volume_ratio']):.1f}× average")
        return {"rules": rules, "now": now}
    return {"rules": [f"Runs {StrategyNames.get_display_name(s.name)}."], "now": now}


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
            "backtest": ({k: (k == ENABLE_KEYS.get(pot.strategy.name)) for k in ENABLE_KEYS.values()}
                         if pot.strategy is not None and pot.strategy.name in ENABLE_KEYS else None),
            "buy_size": pot.order_pct, "max_buys_per_day": pot.max_buys_per_day,
            **_rule(pot, config, price),
        })
    used = {p.strategy.name for p in manager.pots.values() if p.strategy}
    choices = []
    if hasattr(manager, "strategy_choices"):
        from pots import POT_STRATEGIES
        for c in manager.strategy_choices():
            sname = POT_STRATEGIES.get(c["key"])
            choices.append({**c, "blurb": CHOICE_BLURBS.get(c["key"], ""),
                            "running_in": [p.label for p in manager.pots.values()
                                           if p.strategy is not None and p.strategy.name == sname]})
    return {"pots": pots, "unused_controls": UNUSED_CONTROLS, "strategy_choices": choices,
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
    after = {k: _live_value(k, pot, config) for k in allowed}
    after.update({c["key"]: c["after"] for c in out})
    for lo, hi in ORDERED_PAIRS:
        if lo in after and hi in after and after[lo] is not None and after[hi] is not None \
                and after[lo] >= after[hi]:
            raise ValueError(f"{FIELDS[lo]['label']} must be less than {FIELDS[hi]['label'].lower()}")
    return out


LIVE_KEYS = set(FIELDS)


def live_keys(manager) -> set:
    """Settings the running pots trade with right now."""
    return set(_users(manager))
