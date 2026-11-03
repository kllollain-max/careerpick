"""Preference matching must not target subscribers with missing/unknown tags."""
import unittest
from scripts.alert_preference_matcher import matches

JOB = {"title": "행정 사무직 채용", "org": "공공기관", "desc": "경영.회계.사무",
       "region": "서울", "emp": ["정규직"], "edu": ["학력무관"], "cat": "공공기관 공식 공고"}

class PreferenceMatcherTests(unittest.TestCase):
    def test_no_preferences_no_target(self):
        self.assertFalse(matches(JOB, {}))
        self.assertFalse(matches(JOB, {"cp_preferences_set": "no", "cp_schema": "2"}))
    def test_stale_yes_flag_without_filters_does_not_target_everyone(self):
        self.assertFalse(matches(JOB, {"cp_preferences_set": "yes", "cp_schema": "2"}))
        self.assertFalse(matches(JOB, {"cp_preferences_set": "yes", "cp_schema": "2", "cp_keywords": "   "}))

    def test_region_match(self):
        tags = {"cp_preferences_set": "yes", "cp_schema": "2", "cp2_region_1": "서울"}
        self.assertTrue(matches(JOB, tags))
        tags["cp2_region_1"] = "부산"
        self.assertFalse(matches(JOB, tags))
    def test_space_separated_keywords(self):
        tags = {"cp_preferences_set": "yes", "cp_schema": "2", "cp_keywords": "없는단어 사무"}
        self.assertTrue(matches(JOB, tags))
        tags["cp_keywords"] = "없는단어 전혀없는단어"
        self.assertFalse(matches(JOB, tags))

    def test_dimensions_and_keywords(self):
        tags = {"cp_preferences_set": "yes", "cp_schema": "2", "cp2_region_1": "서울",
                "cp2_employment_1": "정규직", "cp_keywords": "전산, 사무"}
        self.assertTrue(matches(JOB, tags))
        tags["cp2_employment_1"] = "계약직"
        self.assertFalse(matches(JOB, tags))

if __name__ == "__main__":
    unittest.main()
