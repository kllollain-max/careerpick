"""Schema v4 compact OneSignal profile regression tests."""
import json
import unittest
from scripts.alert_preference_matcher import matches

class PackedProfileTests(unittest.TestCase):
    def setUp(self):
        self.job = {"id":"job-1","title":"전기직 채용","region":"서울, 경기","emp":"정규직"}
        self.profile = {"v":4,"region":["경기"],"employment":["정규직"],
                        "education":[],"category":[],"keywords":""}

    def tags(self, profile=None):
        return {"cp_optin":"yes","cp_profile":json.dumps(self.profile if profile is None else profile)}

    def test_matching_packed_profile(self):
        self.assertTrue(matches(self.job, self.tags()))

    def test_region_mismatch(self):
        self.assertFalse(matches(self.job, self.tags({**self.profile,"region":["부산"]})))

    def test_nationwide_region_is_candidate(self):
        job = {**self.job, "region": "전국"}
        self.assertTrue(matches(job, self.tags()))

    def test_nationwide_does_not_override_employment(self):
        job = {**self.job, "region": "전국", "emp": "인턴"}
        self.assertFalse(matches(job, self.tags()))

    def test_no_optin(self):
        self.assertFalse(matches(self.job, {"cp_profile":json.dumps(self.profile)}))

    def test_malformed_profile_does_not_fallback(self):
        tags={"cp_optin":"yes","cp_profile":"{bad","cp_schema":"2",
              "cp_preferences_set":"yes","cp2_region_1":"경기"}
        self.assertFalse(matches(self.job,tags))

    def test_empty_profile(self):
        self.assertFalse(matches(self.job,self.tags({"v":4})))

    def test_packed_keywords_match(self):
        tags=self.tags({**self.profile,"region":[],"employment":[],
                        "keywords":"전기직"})
        self.assertTrue(matches(self.job,tags))

    def test_packed_keywords_reject_mismatch(self):
        tags=self.tags({**self.profile,"region":[],"employment":[],
                        "keywords":"간호사"})
        self.assertFalse(matches(self.job,tags))

    def test_boolean_schema_version_is_rejected(self):
        self.assertFalse(matches(self.job,self.tags({**self.profile,"v":True})))

    def test_oversized_keyword_is_rejected(self):
        self.assertFalse(matches(self.job,self.tags({**self.profile,"keywords":"x"*201})))

    def test_oversized_region_is_rejected(self):
        self.assertFalse(matches(self.job,self.tags({**self.profile,"region":["x"*101]})))

    def test_legacy_v3(self):
        self.assertTrue(matches(self.job,{"cp_schema":"3","cp_preferences_set":"yes",
                                         "cp3_region":"경기"}))

if __name__ == "__main__":
    unittest.main()
