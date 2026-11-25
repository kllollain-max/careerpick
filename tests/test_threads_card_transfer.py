import base64
import hashlib
import unittest
from scripts.threads_card_transfer import select_entry, pack


class CardTransferTests(unittest.TestCase):
    def test_exact_missing_card_only(self):
        e = {"notice_id": "a123", "scheduled_at": "future",
             "writer": {"status": "ready", "review": {"v5": {}}}}
        r = {"refused": [{"notice_id": "a123", "slot": "future",
                         "reason": "CARD_VISUAL_REVIEW_REQUIRED"}]}
        self.assertEqual(select_entry(r, {"entries": [e]}), e)
        r["refused"][0]["reason"] = "REVIEW_SOURCE_STALE"
        self.assertIsNone(select_entry(r, {"entries": [e]}))
        r["refused"][0]["reason"] = "CARD_VISUAL_REVIEW_REQUIRED"
        e["writer"]["review"]["v5"]["card_visual_review"] = {"status": "passed"}
        self.assertIsNone(select_entry(r, {"entries": [e]}))

    def test_exact_bytes_and_no_approval(self):
        j = {"id": "a123"}
        b = pack(j, "digest", b"jpeg", b"png")
        self.assertFalse(b["automatic_approval"])
        self.assertFalse(b["meta_posted"])
        self.assertEqual(b["status"], "visual_review_required")
        self.assertEqual(base64.b64decode(b["assets"]["jpeg"]["base64"]), b"jpeg")
        self.assertEqual(b["assets"]["preview"]["sha256"], hashlib.sha256(b"png").hexdigest())
