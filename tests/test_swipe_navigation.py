import unittest

import web_dashboard
from system_health_page import system_page


class SwipeNavigationTests(unittest.TestCase):
    def test_tablet_shell_contains_three_views_and_expected_swipes(self):
        html = web_dashboard._page(30).decode("utf-8")
        self.assertIn('width: 300vw', html)
        self.assertIn('id="system-frame"', html)
        self.assertIn('activeView === "dashboard" && dx > 0', html)
        self.assertIn('showView("system")', html)
        self.assertIn('activeView === "dashboard" && dx < 0', html)
        self.assertIn('showView("month")', html)
        self.assertIn('family-display-system-swipe-left', html)

    def test_system_page_swipe_left_returns_to_parent_dashboard(self):
        html = system_page().decode("utf-8")
        self.assertIn('target="_top"', html)
        self.assertIn('family-display-system-swipe-left', html)
        self.assertIn('window.parent.postMessage', html)
        self.assertIn('window.location.href = "/"', html)


if __name__ == "__main__":
    unittest.main()
