"""Dashboard layout with money pots: pots first, no paper panel flash.

Before, the Money Pots panel started hidden and the old paper panel started
visible, so the page jumped once /api/pots answered.
"""

import threading

import auth as _auth_module  # noqa: F401  (import order, see test_manual_trade_api)
from database import initialize_database
from pots import POT_TREND
from tests.test_pots import live_pots, make_config


def _page(with_pots):
    from app import create_app, init_services
    from auth import get_auth_config
    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False)
    pots, _, _, sm, exchange = live_pots(db, config=config)
    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), exchange, sm, config)
    state.set_pot_manager(pots if with_pots else None)
    try:
        return app.test_client().get("/ui").get_data(as_text=True)
    finally:
        state.set_pot_manager(None)


def _tag(html, element_id):
    start = html.index(f'id="{element_id}"')
    return html[html.rindex("<", 0, start):html.index(">", start)]


def test_with_pots_the_pots_panel_shows_and_the_paper_panel_is_hidden():
    html = _page(with_pots=True)
    assert "display: none" not in _tag(html, "pots-panel")
    assert "display: none" in _tag(html, "paper-panel")
    assert "window.__potsOnAtLoad = true" in html
    # Order: cards, pots, manual trading, price chart, signals, recent trades
    order = [html.index(m) for m in ('class="summary"', 'id="pots-panel"', 'id="manual-trading-panel"',
                                     'class="chart-container"', 'id="strategy-signals-grid"', 'id="trades-panel"')]
    assert order == sorted(order)
    # Styles sit in the head, before any panel
    assert html.rindex("<style>") < html.index('class="summary"')


def test_without_pots_the_paper_panel_shows():
    html = _page(with_pots=False)
    assert "display: none" in _tag(html, "pots-panel")
    assert "display: none" not in _tag(html, "paper-panel")
    assert "window.__potsOnAtLoad = false" in html
