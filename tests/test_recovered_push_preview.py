import unittest
from datetime import datetime, timedelta, timezone
from scripts.push_preview import candidates, event_deduplicate, matched_job_tags, matching_preference_tags, preview_profile_matches

KST = timezone(timedelta(hours=9))

class PushPreviewTests(unittest.TestCase):
    def test_no_unsafe_tag_matching(self):
        self.assertIsNone(matched_job_tags({"region": "서울"}))

    def test_multiple_selections_or_and_fields(self):
        job={"title":"공기업 사무직", "region":"서울", "emp":["정규직"], "edu":["학력무관"], "cat":"행정"}
        self.assertTrue(matching_preference_tags(job, {"region":["경기","서울"], "emp":["정규직"], "edu":["고졸 가능"], "cat":["행정"], "kw":"사무"}))
        self.assertFalse(matching_preference_tags(job, {"region":["부산"], "emp":["정규직"]}))
        self.assertFalse(matching_preference_tags(job, {"region":["서울"], "emp":["인턴"]}))
        self.assertFalse(matching_preference_tags(job, {"kw":"의사 간호사"}))

    def test_real_alio_category_does_not_imply_job_specialty(self):
        job={"title":"행정 지원", "org":"공공기관", "cat":"공공기관 공식 공고",
             "desc":"사무.행정", "region":"서울", "emp":["계약직"], "edu":["학력무관"]}
        self.assertTrue(matching_preference_tags(job, {"kw":"사무"}))
        self.assertFalse(matching_preference_tags(job, {"cat":["간호"]}))
        self.assertEqual(len(preview_profile_matches([dict(job,event_id="new:a1")],{"kw":"사무"})),1)
        self.assertEqual(preview_profile_matches([dict(job,event_id="new:a1")],{"kw":"간호"}),[])

    def test_unknown_region_not_over_targeted(self):
        self.assertFalse(matching_preference_tags({"region":""}, {"region":["서울"]}))

    def test_deduplication(self):
        events = [{"event_id": "new:a1"}, {"event_id": "new:a1"}, {"event_id": "d1:a1:2026-10-25"}]
        self.assertEqual([x["event_id"] for x in event_deduplicate(events, {"new:a1"})], ["d1:a1:2026-10-25"])

    def test_expired_job_excluded(self):
        now = datetime(2026, 10, 25, 12, tzinfo=KST)
        p = {"alio": True, "id": "a1", "title": "Test", "due": (now-timedelta(days=1)).isoformat()}
        self.assertEqual(candidates([p], now), [])

    def test_d1(self):
        now = datetime(2026, 10, 25, 12, tzinfo=KST)
        p = {"alio": True, "id": "a1", "title": "Test", "due": (now+timedelta(days=1)).isoformat()}
        self.assertEqual([x["kind"] for x in candidates([p], now)], ["deadline_d1"])

if __name__ == "__main__":
    unittest.main()
