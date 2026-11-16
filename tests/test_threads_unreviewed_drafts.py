"""Unreviewed draft writer safety regression tests; no network or publication."""
import unittest
from scripts.threads_unreviewed_drafts import build_drafts


class DraftWriterTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {
            "automatic_approval": False, "meta_posted": False,
            "missing_slots": ["2026-11-17T08:00:00+09:00"],
            "candidates": [{
                "notice_id": "a123", "org": "검증대상 기관",
                "title": "전산직 채용", "employment": "정규직",
                "application_period": {"end": "2026-11-20", "date_only": True},
                "official_url": "https://example.org/notice",
                "source_post_sha256": "abc", "source_detail_sha256": "def",
            }],
        }

    def test_draft_is_never_approved_or_posted(self):
        result = build_drafts(self.handoff)
        self.assertEqual(len(result["drafts"]), 1)
        self.assertFalse(result["approved_for_queue"])
        draft = result["drafts"][0]
        self.assertEqual(draft["status"], "unreviewed")
        self.assertFalse(draft["approved_for_queue"])
        self.assertFalse(draft["meta_posted"])
        self.assertNotIn("https://", draft["draft_text"])

    def test_timestamp_deadline_keeps_verified_clock(self):
        candidate = {**self.handoff['candidates'][0],
                     'application_period': {'end': '2026-11-20T14:00:00+09:00', 'date_only': False}}
        draft = build_drafts({**self.handoff, 'candidates': [candidate]})['drafts'][0]
        self.assertIn('14:00 +0900', draft['draft_text'])
        self.assertNotIn('마감 시각 원문 확인', draft['draft_text'])

    def test_expired_notice_is_excluded(self):
        candidate = {**self.handoff['candidates'][0],
                     'application_period': {'end': '2026-11-16T10:00:00+09:00', 'date_only': False}}
        self.assertEqual(build_drafts({**self.handoff, 'candidates': [candidate]})['drafts'], [])

    def test_deadline_day_without_clock_is_excluded(self):
        candidate = {**self.handoff['candidates'][0],
                     'application_period': {'end': '2026-11-17', 'date_only': True}}
        self.assertEqual(build_drafts({**self.handoff, 'candidates': [candidate]})['drafts'], [])

    def test_reject_unsafe_handoff(self):
        for flag in ("automatic_approval", "meta_posted"):
            handoff = {**self.handoff, flag: True}
            with self.assertRaises(ValueError):
                build_drafts(handoff)

    def test_no_draft_without_application_period(self):
        handoff = {**self.handoff, "candidates": [
            {**self.handoff["candidates"][0], "application_period": None}
        ]}
        self.assertEqual(build_drafts(handoff)["drafts"], [])

    def test_no_draft_without_source_identity(self):
        handoff = {**self.handoff, "candidates": [
            {**self.handoff["candidates"][0], "notice_id": ""}
        ]}
        self.assertEqual(build_drafts(handoff)["drafts"], [])


if __name__ == "__main__":
    unittest.main()
