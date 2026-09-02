"""Sprint 11 timezone conversion and DST-safety tests."""

import unittest
from datetime import datetime, timezone

from timezones import TimezoneError, format_plan_datetime, get_timezone, is_valid_timezone, local_to_utc, utc_to_local


class TimezoneTests(unittest.TestCase):
    def assert_utc(self, local_value, zone, expected):
        self.assertEqual(local_to_utc(local_value, zone), expected.replace(tzinfo=timezone.utc))

    def test_supported_iana_zones_and_invalid_values(self):
        for key in ("Europe/Dublin", "America/New_York", "Africa/Lagos", "Asia/Tokyo", "UTC"):
            self.assertTrue(is_valid_timezone(key))
            self.assertEqual(get_timezone(key).key, key)
        for value in ("", "GMT+1", "+01:00", "Europe/Not_A_Zone", "../UTC", "<script>alert(1)</script>"):
            self.assertFalse(is_valid_timezone(value))

    def test_summer_and_winter_offsets(self):
        self.assert_utc(datetime(2026, 7, 15, 18), "Europe/Dublin", datetime(2026, 7, 15, 17))
        self.assert_utc(datetime(2026, 1, 15, 18), "Europe/Dublin", datetime(2026, 1, 15, 18))
        self.assert_utc(datetime(2026, 7, 15, 18), "America/New_York", datetime(2026, 7, 15, 22))
        self.assert_utc(datetime(2026, 1, 15, 18), "America/New_York", datetime(2026, 1, 15, 23))
        self.assert_utc(datetime(2026, 7, 15, 18), "Africa/Lagos", datetime(2026, 7, 15, 17))
        self.assert_utc(datetime(2026, 7, 15, 18), "Asia/Tokyo", datetime(2026, 7, 15, 9))
        self.assert_utc(datetime(2026, 7, 15, 18), "UTC", datetime(2026, 7, 15, 18))

    def test_round_trip_preserves_a_valid_wall_time(self):
        local = datetime(2026, 8, 20, 19, 45)
        instant = local_to_utc(local, "Europe/Dublin")
        self.assertEqual(utc_to_local(instant, "Europe/Dublin").replace(tzinfo=None), local)

    def test_dublin_dst_gap_and_fold_are_rejected(self):
        with self.assertRaisesRegex(TimezoneError, "does not exist"):
            local_to_utc(datetime(2026, 3, 29, 1, 30), "Europe/Dublin")
        with self.assertRaisesRegex(TimezoneError, "occurs twice"):
            local_to_utc(datetime(2026, 10, 25, 1, 30), "Europe/Dublin")

    def test_new_york_dst_gap_and_fold_are_rejected(self):
        with self.assertRaisesRegex(TimezoneError, "does not exist"):
            local_to_utc(datetime(2026, 3, 8, 2, 30), "America/New_York")
        with self.assertRaisesRegex(TimezoneError, "occurs twice"):
            local_to_utc(datetime(2026, 11, 1, 1, 30), "America/New_York")

    def test_format_includes_local_time_and_canonical_zone(self):
        value = format_plan_datetime(datetime(2026, 7, 15, 17), "Europe/Dublin", compact=True)
        self.assertEqual(value, "Wed 15 Jul \u00b7 18:00 \u2014 Europe/Dublin")


if __name__ == "__main__":
    unittest.main()
