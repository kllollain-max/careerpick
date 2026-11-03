"""Offline regression coverage for compact OneSignal preference tags."""
import unittest
from scripts.alert_preference_matcher import matches

class CompactTagTests(unittest.TestCase):
    def setUp(self):
        self.job = {"title": "전기 기술직 채용", "region": "서울, 경기",
                    "emp": "정규직", "edu": "학력무관", "cat": "기술"}

    def test_compact_match(self):
        tags = {"cp_schema": "3", "cp_preferences_set": "yes",
                "cp3_region": "강원|경기", "cp3_employment": "정규직"}
        self.assertTrue(matches(self.job, tags))

    def test_compact_reject_mismatch(self):
        tags = {"cp_schema": "3", "cp_preferences_set": "yes",
                "cp3_region": "부산"}
        self.assertFalse(matches(self.job, tags))

    def test_empty_compact_preferences_fail_closed(self):
        self.assertFalse(matches(self.job, {"cp_schema": "3", "cp_preferences_set": "yes"}))

    def test_legacy_schema_two_still_matches(self):
        tags = {"cp_schema": "2", "cp_preferences_set": "yes",
                "cp2_region_1": "경기"}
        self.assertTrue(matches(self.job, tags))

if __name__ == "__main__":
    unittest.main()
