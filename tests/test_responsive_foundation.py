"""Fast wiring checks for the reusable responsive foundation."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ResponsiveFoundationTests(unittest.TestCase):
    def test_shared_layout_defines_contract_primitives(self):
        css = (ROOT / "static/css/layout.css").read_text(encoding="utf-8")
        for token in ("--page-gutter", "--content-max", "--content-wide", "--card-radius", "--control-height"):
            self.assertIn(token, css)
        for primitive in (".friendly-container", ".friendly-card", ".friendly-grid", ".app-header", ".app-nav"):
            self.assertIn(primitive, css)
        self.assertIn("*,*::before,*::after", css)
        self.assertIn("min-width:0", css)

    def test_major_pages_load_shared_layout(self):
        for template in (
            "home.html", "register.html", "login.html", "dashboard.html", "profile_form.html",
            "profile.html", "discover.html", "person_profile.html",
        ):
            source = (ROOT / "templates" / template).read_text(encoding="utf-8")
            self.assertIn("css/layout.css", source, template)

    def test_authenticated_pages_use_shared_header(self):
        for template in ("dashboard.html", "profile_form.html", "profile.html", "discover.html", "person_profile.html"):
            source = (ROOT / "templates" / template).read_text(encoding="utf-8")
            self.assertIn("app-header", source, template)
            self.assertIn("app-nav", source, template)

    def test_discover_has_accessible_mobile_filter_disclosure(self):
        template = (ROOT / "templates/discover.html").read_text(encoding="utf-8")
        script = (ROOT / "static/js/discover.js").read_text(encoding="utf-8")
        self.assertIn("<details", template)
        self.assertIn("<summary", template)
        self.assertIn("data-discovery-filters", template)
        self.assertIn('matchMedia("(max-width: 767px)")', script)

    def test_standard_viewport_matrix_is_reusable(self):
        helper = (ROOT / "tests/responsive_helper.py").read_text(encoding="utf-8")
        for width in (320, 360, 375, 390, 412, 480, 768, 1024, 1280, 1440):
            self.assertIn(str(width), helper)
        self.assertIn("verify_responsive_layout", helper)


if __name__ == "__main__":
    unittest.main()
