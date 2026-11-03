"""Region matching for ALIO multi-location job notices; no API calls."""
import unittest
from scripts.alert_preference_matcher import matches, region_tokens

class MultiRegionMatchTests(unittest.TestCase):
    def setUp(self):
        self.tags = {"cp_preferences_set": "yes", "cp_schema": "2",
                     "cp2_region_1": "경기"}

    def test_comma_separated_region_matches(self):
        self.assertTrue(matches({"region": "서울, 경기", "title": "채용"}, self.tags))

    def test_other_region_does_not_match(self):
        self.assertFalse(matches({"region": "서울, 강원", "title": "채용"}, self.tags))

    def test_no_substring_false_positive(self):
        self.assertFalse(matches({"region": "경기도 외", "title": "채용"}, self.tags))

    def test_newline_and_whitespace_separated(self):
        self.assertEqual(region_tokens("서울\n경기  강원"), ["서울", "경기", "강원"])

    def test_list_and_slash_separated(self):
        self.assertEqual(region_tokens(["서울/경기", "강원"]), ["서울", "경기", "강원"])

if __name__ == "__main__":
    unittest.main()
