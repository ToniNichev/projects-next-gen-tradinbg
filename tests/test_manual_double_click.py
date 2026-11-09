"""Manual buy/sell can't go through twice by accident.

If the answer to a confirmed buy is lost (network blip) the page re-enables
Confirm; clicking it again resends the same request_id and gets the first
result back. A second buy within 10 s from anywhere (another tab) is refused.
"""

import time

from app.api import trading
from tests import test_manual_trade_api as base


class DoubleClickTests(base.ManualTradeAPITests):
    def _buy(self, **body):
        with self._patched_config():
            return self.client.post("/api/manual/buy", json={"position_size": 0.25, **body})

    def test_same_confirmation_trades_once(self):
        first = self._buy(request_id="abc")
        self.assertEqual(first.status_code, 200, first.get_json())
        usdt_after_one = self.trader.usdt_balance
        again = self._buy(request_id="abc")
        self.assertEqual(again.status_code, 200)
        data = again.get_json()
        self.assertTrue(data["duplicate"])
        self.assertEqual(data["trade"], first.get_json()["trade"])
        self.assertEqual(self.trader.usdt_balance, usdt_after_one)  # no second buy

    def test_second_buy_within_cooldown_is_refused(self):
        self.assertEqual(self._buy(request_id="one").status_code, 200)
        usdt = self.trader.usdt_balance
        r = self._buy(request_id="two")
        self.assertEqual(r.status_code, 429)
        self.assertIn("ago", r.get_json()["error"])
        self.assertEqual(self.trader.usdt_balance, usdt)

    def test_a_later_buy_is_allowed_after_selling(self):
        self.assertEqual(self._buy(request_id="one").status_code, 200)
        with self._patched_config():
            self.assertEqual(self.client.post("/api/manual/sell", json={"request_id": "s1"}).status_code, 200)
        trading._manual_last["buy"] = time.time() - trading.MANUAL_COOLDOWN - 1
        self.assertEqual(self._buy(request_id="two").status_code, 200)

    def test_no_second_buy_while_holding(self):
        """2026-11-05 review: a second buy left the first stop order on the
        exchange next to a new one for all the pot's BTC."""
        self.assertEqual(self._buy(request_id="one").status_code, 200)
        trading._manual_last["buy"] = time.time() - trading.MANUAL_COOLDOWN - 1
        r = self._buy(request_id="two")
        self.assertEqual(r.status_code, 409)
        self.assertIn("Sell it first", r.get_json()["error"])

    def test_selling_right_after_buying_is_allowed(self):
        self.assertEqual(self._buy(request_id="b").status_code, 200)
        with self._patched_config():
            r = self.client.post("/api/manual/sell", json={"request_id": "s"})
        self.assertEqual(r.status_code, 200, r.get_json())

    def test_failed_buy_does_not_start_the_cooldown(self):
        with self._patched_config():
            bad = self.client.post("/api/manual/buy", json={"position_size": 5, "request_id": "x"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self._buy(request_id="x2").status_code, 200)



# Don't re-run the parent's tests through this subclass
for _name in [n for n in vars(base.ManualTradeAPITests) if n.startswith("test_")]:
    setattr(DoubleClickTests, _name, None)
