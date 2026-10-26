"""Running the tests must never send real alerts."""

import time

import notify


def test_notifications_are_captured_not_sent(no_real_notifications):
    notify.send_notification("hello", "from tests", severity="critical")
    for _ in range(50):
        if no_real_notifications:
            break
        time.sleep(0.01)
    assert no_real_notifications == [("hello", "from tests", "critical")]
