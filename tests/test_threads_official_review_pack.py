"""Live official proof packets are private review aids, never approvals."""
import hashlib
import unittest
from scripts.threads_official_review_pack import read_official, build_packet


class Response:
    def __init__(self, body=b"<html><title>Official notice</title><body>Notice 1</body></html>",
                 url="https://www.alio.go.kr/notice", mime="text/html; charset=utf-8"):
        self.body, self.url = body, url
        self.headers = {"Content-Type": mime}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self.url

    def read(self, _):
        return self.body


class Opener:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def open(self, req, timeout):
        self.calls += 1
        return self.response


class EvidencePacketTests(unittest.TestCase):
    def setUp(self):
        self.url = "https://www.alio.go.kr/notice"
        self.bundle = {"status": "review_required", "approved_for_queue": False,
                       "drafts": [{"notice_id": "a123", "status": "unreviewed",
                                   "suggested_slot": "2026-11-17T08:00:00+09:00",
                                   "official_url_for_private_review": self.url,
                                   "draft_text": "official notice"}]}

    def test_official_bytes_digest_and_html_title_are_collected(self):
        body = "<html><title>공지</title><script>bad</script><body>채용 공고</body></html>".encode()
        evidence = read_official(self.url, opener=Opener(Response(body)))
        self.assertEqual(evidence["sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(evidence["official_page_title"], "공지")
        self.assertIn("채용 공고", evidence["visible_text_excerpt"])
        self.assertNotIn("bad", evidence["visible_text_excerpt"])

    def test_offsite_final_redirect_blocks_read(self):
        with self.assertRaisesRegex(ValueError, "OFFICIAL_FINAL_URL_NOT_ALLOWED"):
            read_official(self.url, opener=Opener(Response(url="https://evil.example/post")))

    def test_source_success_still_requires_all_manual_reviews(self):
        verified = {"url": self.url, "final_url": self.url,
                    "sha256": "a" * 64, "size_bytes": 123}
        packet = build_packet(self.bundle, fetch=lambda _: verified)
        self.assertEqual(packet["checked"], 1)
        self.assertFalse(packet["automatic_approval"])
        self.assertFalse(packet["approved_for_queue"])
        self.assertFalse(packet["meta_posted"])
        self.assertEqual(packet["records"][0]["publisher_validate_entry"], "not_run")
        self.assertEqual(packet["records"][0]["semantic_review"], "required")

    def test_missing_or_untrusted_official_url_does_not_fetch(self):
        self.bundle["drafts"][0]["official_url_for_private_review"] = "https://example.com"
        def forbidden(_):
            raise AssertionError("must not fetch")
        packet = build_packet(self.bundle, fetch=forbidden)
        self.assertEqual(packet["checked"], 0)
        self.assertEqual(packet["records"][0]["block_reason"], "OFFICIAL_URL_NOT_ALLOWED")

    def test_partial_and_duplicate_drafts_do_not_create_approval(self):
        self.bundle["drafts"].append(dict(self.bundle["drafts"][0]))
        self.bundle["drafts"].append({"notice_id": "a456", "status": "unreviewed",
                                      "official_url_for_private_review": "https://www.alio.go.kr/no"})
        packet = build_packet(self.bundle, fetch=lambda url: {"url": url, "sha256": "x"})
        self.assertEqual(len(packet["records"]), 2)
        self.assertEqual(packet["checked"], 0)
        self.assertEqual(packet["records"][0]["block_reason"], "OFFICIAL_EVIDENCE_INVALID")

    def test_rejects_unsafe_input_bundle(self):
        self.bundle["approved_for_queue"] = True
        with self.assertRaisesRegex(ValueError, "UNREVIEWED_DRAFT_BUNDLE_REQUIRED"):
            build_packet(self.bundle)


    def test_exact_cleaneye_fingerprint_uses_employer_notice_not_unreachable_feed_page(self):
        from scripts.threads_official_review_pack import independently_located_notice
        draft = {"notice_id": "cleaneye-80820",
                 "source_post_sha256": "8d3752df0454401d33229336de56bbfebe204a1337ee98ca1ac6a87f458528f1",
                 "source_detail_sha256": "c67be70000794ee30457361c24cb0ba633e4efc2d2b145790074b1dde8b0834e",
                 "official_url_for_private_review": "https://job.cleaneye.go.kr/user/ypCareersData.do?idx=80820"}
        found = independently_located_notice(draft)
        self.assertEqual(found, "https://www.smrtg.co.kr/employment/stffPbanInfo.do?stffPbanNo=2026-0155")
        recorded = []
        packet = build_packet({"status": "review_required", "approved_for_queue": False,
                               "drafts": [{**draft, "status": "unreviewed"}]},
                              fetch=lambda url: (recorded.append(url) or
                                  {"url": url, "sha256": "b" * 64, "size_bytes": 100}))
        self.assertEqual(recorded, [found])
        self.assertEqual(packet["checked"], 1)
        self.assertFalse(packet["approved_for_queue"])
        draft["source_detail_sha256"] = "c" * 64
        self.assertEqual(independently_located_notice(draft), draft["official_url_for_private_review"])



if __name__ == "__main__":
    unittest.main()
