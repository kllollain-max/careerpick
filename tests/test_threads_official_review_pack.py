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

    def test_first_eight_unavailable_do_not_starve_later_official_source(self):
        import urllib.error
        self.bundle['drafts'] = [dict(self.bundle['drafts'][0], notice_id=str(i),
             official_url_for_private_review=f'https://source{i//4}.go.kr/{i}') for i in range(24)]
        called = []
        def fetch(url):
            called.append(url)
            if int(url.rsplit('/', 1)[-1]) < 8:
                raise urllib.error.URLError('temporary outage')
            return {'url': url, 'sha256': 'a' * 64}
        result = build_packet(self.bundle, fetch=fetch)
        self.assertEqual(result['checked'], 8)
        self.assertEqual(result['attempted'], 16)
        self.assertFalse(result['approved_for_queue'])
        self.assertFalse(result['meta_posted'])
        self.assertEqual([r['notice_id'] for r in result['records']], list(map(str, range(16))))

    def test_outage_defers_same_host_but_checks_later_alternative(self):
        import urllib.error
        self.bundle['drafts'] = [dict(self.bundle['drafts'][0], notice_id=str(i),
             official_url_for_private_review=f'https://job.cleaneye.go.kr/{i}') for i in range(21)]
        self.bundle['official_source_alternatives'] = [{
             'notice_id': 'alio-alternative', 'status': 'unreviewed',
             'official_url_for_private_review': 'https://job.alio.go.kr/notice'}]
        def fetch(url):
            if 'cleaneye' in url:
                raise urllib.error.URLError('unavailable')
            return {'url': url, 'sha256': 'a' * 64}
        result = build_packet(self.bundle, fetch=fetch)
        self.assertEqual(result['attempted'], 5)
        self.assertEqual(result['checked'], 1)
        self.assertEqual(len(result['deferred_notice_ids']), 17)
        self.assertEqual(result['unavailable_hosts'], ['job.cleaneye.go.kr'])
        self.assertFalse(result['approved_for_queue'])

    def test_total_failed_source_attempts_are_bounded(self):
        import urllib.error
        self.bundle['drafts'] = [dict(self.bundle['drafts'][0], notice_id=str(i), official_url_for_private_review=f'https://source{i}.go.kr/{i}') for i in range(30)]
        def fetch(url):
            raise urllib.error.URLError('temporary outage')
        result = build_packet(self.bundle, fetch=fetch)
        self.assertEqual(result['attempted'], 24)
        self.assertEqual(result['checked'], 0)

    def test_official_get_retries_transient_503_before_reading_bytes(self):
        from unittest.mock import Mock, patch
        import urllib.error
        response = Response()
        opener = Mock()
        opener.open.side_effect = [urllib.error.HTTPError(self.url, 503, '', {}, None), response]
        with patch('scripts.threads_http.time.sleep') as sleeper:
            result = read_official(self.url, opener=opener)
        self.assertEqual(opener.open.call_count, 2)
        sleeper.assert_called_once_with(2)
        self.assertTrue(result['text_available'])

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




    def test_yangju_81438_pinned_official_city_notice_and_annexes_never_autoapprove(self):
        from scripts.threads_official_review_pack import (
            CANONICAL_REVIEW_URLS, CANONICAL_REVIEW_ANNEXES,
            independently_located_notice,
        )
        from scripts.threads_reviewed_ingest import official_url_allowed

        pin = CANONICAL_REVIEW_URLS["cleaneye-81438"]
        fallback = "https://job.cleaneye.go.kr/user/ypCareersData.do?idx=81438"
        draft = {
            "notice_id": "cleaneye-81438", "status": "unreviewed",
            "source_post_sha256": pin["source_post_sha256"],
            "source_detail_sha256": pin["source_detail_sha256"],
            "official_url_for_private_review": fallback,
        }
        annexes = CANONICAL_REVIEW_ANNEXES["cleaneye-81438"]
        self.assertEqual(len(annexes), 2)
        self.assertEqual(independently_located_notice(draft), pin["url"])
        self.assertTrue(all(official_url_allowed(x) for x in [pin["url"], *annexes]))

        seen = []
        def fetched(url):
            seen.append(url)
            return {
                "url": url, "sha256": "a" * 64, "size_bytes": 281584,
                "pdf_magic_valid": url in annexes,
                "checked_at": "2026-11-21T11:45:00+09:00",
            }
        packet = build_packet({
            "status": "review_required", "approved_for_queue": False,
            "drafts": [draft],
        }, fetch=fetched)
        self.assertEqual(seen, [pin["url"], *annexes])
        self.assertEqual(packet["checked"], 1)
        self.assertEqual(packet["records"][0]["attachment_status"],
                         "all_raw_pdf_sha256_captured")
        self.assertFalse(packet["approved_for_queue"])
        self.assertFalse(packet["automatic_approval"])
        self.assertFalse(packet["meta_posted"])
        self.assertEqual(packet["records"][0]["publisher_validate_entry"],
                         "not_run")
        self.assertEqual(packet["records"][0]["semantic_review"], "required")

        # Source identity change invalidates the exact pin and prevents annex
        # digests from being attributed to another posting or a newer version.
        changed = dict(draft, source_detail_sha256="b" * 64)
        self.assertEqual(independently_located_notice(changed), fallback)
        seen.clear()
        second = build_packet({
            "status": "review_required", "approved_for_queue": False,
            "drafts": [changed],
        }, fetch=fetched)
        self.assertEqual(seen, [fallback])
        self.assertNotIn("attachment_receipts", second["records"][0])
        different_id = dict(draft, notice_id="cleaneye-81439")
        self.assertEqual(independently_located_notice(different_id), fallback)

    def test_cleaneye_81115_pinned_two_real_pdf_sources_are_review_only(self):
        from scripts.threads_official_review_pack import (
            CANONICAL_REVIEW_URLS, CANONICAL_REVIEW_ANNEXES, independently_located_notice)
        pin = CANONICAL_REVIEW_URLS["cleaneye-81115"]
        draft = {"notice_id": "cleaneye-81115", "status": "unreviewed",
                 "source_post_sha256": pin["source_post_sha256"],
                 "source_detail_sha256": pin["source_detail_sha256"],
                 "official_url_for_private_review":
                 "https://job.cleaneye.go.kr/user/ypCareersData.do?idx=81115"}
        annexes = CANONICAL_REVIEW_ANNEXES["cleaneye-81115"]
        self.assertEqual(len(annexes), 2)
        self.assertEqual(independently_located_notice(draft), pin["url"])
        urls_seen = []
        def fetched(url):
            urls_seen.append(url)
            return {"url": url, "sha256": "a" * 64, "size_bytes": 200,
                    "pdf_magic_valid": url in annexes,
                    "checked_at": "2026-11-17T01:00:00+09:00"}
        packet = build_packet({"status": "review_required",
                               "approved_for_queue": False,
                               "drafts": [draft]}, fetch=fetched)
        self.assertEqual(urls_seen, [pin["url"], *annexes])
        self.assertEqual(packet["checked"], 1)
        record = packet["records"][0]
        self.assertEqual(record["attachment_status"],
                         "all_raw_pdf_sha256_captured")
        self.assertEqual(len(record["attachment_receipts"]), 2)
        self.assertFalse(packet["approved_for_queue"])
        self.assertFalse(packet["automatic_approval"])
        self.assertEqual(record["publisher_validate_entry"], "not_run")
        self.assertTrue(record["attachment_review_required"])
        draft["source_detail_sha256"] = "a" * 64
        self.assertEqual(independently_located_notice(draft),
                         draft["official_url_for_private_review"])
        other = dict(draft, notice_id="cleaneye-81116")
        self.assertEqual(independently_located_notice(other),
                         other["official_url_for_private_review"])

    def test_pdf_magic_from_downloaded_bytes_not_content_type_alone(self):
        url = "https://www.alio.go.kr/notice"
        self.assertTrue(read_official(url, opener=Opener(
            Response(body=b"%PDF-1.7\\nbody", mime="application/pdf")))["pdf_magic_valid"])
        self.assertFalse(read_official(url, opener=Opener(
            Response(body=b"<html>error</html>", mime="application/pdf")))["pdf_magic_valid"])

    def test_cleaneye_80848_annex_digest_collection_is_pinned_and_unapproved(self):
        from scripts.threads_official_review_pack import (
            CANONICAL_REVIEW_URLS, CANONICAL_REVIEW_ANNEXES, CANONICAL_REVIEW_BOARDS, independently_located_notice)
        pinned = CANONICAL_REVIEW_URLS["cleaneye-80848"]
        draft = {
            "notice_id": "cleaneye-80848", "status": "unreviewed",
            "source_post_sha256": pinned["source_post_sha256"],
            "source_detail_sha256": pinned["source_detail_sha256"],
            "official_url_for_private_review": "https://job.cleaneye.go.kr/user/ypCareersData.do?idx=80848",
        }
        urls = CANONICAL_REVIEW_ANNEXES["cleaneye-80848"]
        self.assertEqual(len(urls), 3)
        self.assertEqual(independently_located_notice(draft), pinned["url"])
        called = []
        def fetched(url):
            called.append(url)
            return {"url": url, "sha256": "b" * 64, "size_bytes": 100,
                    "pdf_magic_valid": url in urls, "checked_at": "2026-11-16T19:00:00+09:00"}
        packet = build_packet({"status": "review_required", "approved_for_queue": False,
                               "drafts": [draft]}, fetch=fetched)
        record = packet["records"][0]
        self.assertEqual(called, [pinned["url"], *urls, CANONICAL_REVIEW_BOARDS["cleaneye-80848"]["url"]])
        self.assertEqual(record["employer_recruitment_board_receipt"]["status"],
                         "board_bytes_fetched_for_independent_review")
        self.assertFalse(record["employer_recruitment_board_receipt"]["correction_absence_verified"])
        self.assertEqual(record["attachment_status"], "all_raw_pdf_sha256_captured")
        self.assertEqual(len(record["attachment_receipts"]), 3)
        self.assertFalse(packet["approved_for_queue"])
        self.assertFalse(packet["automatic_approval"])
        self.assertEqual(record["publisher_validate_entry"], "not_run")
        self.assertTrue(record["attachment_review_required"])

    def test_cleaneye_80848_non_pdf_or_different_snapshot_cannot_claim_annex_receipts(self):
        from scripts.threads_official_review_pack import CANONICAL_REVIEW_URLS
        pinned = CANONICAL_REVIEW_URLS["cleaneye-80848"]
        draft = {"notice_id": "cleaneye-80848", "status": "unreviewed",
                 "source_post_sha256": pinned["source_post_sha256"],
                 "source_detail_sha256": pinned["source_detail_sha256"]}
        def fetched(url):
            return {"url": url, "sha256": "c" * 64, "pdf_magic_valid": False}
        packet = build_packet({"status": "review_required", "approved_for_queue": False,
                               "drafts": [draft]}, fetch=fetched)
        self.assertEqual(packet["records"][0]["attachment_status"],
                         "raw_pdf_receipts_incomplete")
        self.assertTrue(all(x["status"] == "unverified" for x in
                            packet["records"][0]["attachment_receipts"]))
        self.assertFalse(packet["approved_for_queue"])
        draft["source_detail_sha256"] = "d" * 64
        packet = build_packet({"status": "review_required", "approved_for_queue": False,
                               "drafts": [draft]}, fetch=fetched)
        self.assertNotIn("attachment_receipts", packet["records"][0])


    def test_invalid_employer_board_receipt_fails_closed_without_publishing(self):
        from scripts.threads_official_review_pack import (
            CANONICAL_REVIEW_URLS, CANONICAL_REVIEW_BOARDS)
        pinned = CANONICAL_REVIEW_URLS["cleaneye-80848"]
        board_url = CANONICAL_REVIEW_BOARDS["cleaneye-80848"]["url"]
        draft = {"notice_id": "cleaneye-80848", "status": "unreviewed",
                 "source_post_sha256": pinned["source_post_sha256"],
                 "source_detail_sha256": pinned["source_detail_sha256"]}
        def fetched(url):
            if url == board_url:
                raise ValueError("BOARD_UNAVAILABLE")
            return {"url": url, "sha256": "b" * 64, "size_bytes": 100,
                    "pdf_magic_valid": True}
        packet = build_packet({"status": "review_required", "approved_for_queue": False,
                               "drafts": [draft]}, fetch=fetched)
        receipt = packet["records"][0]["employer_recruitment_board_receipt"]
        self.assertEqual(receipt["status"], "not_verified")
        self.assertEqual(receipt["block_reason"], "BOARD_UNAVAILABLE")
        self.assertFalse(receipt["correction_absence_verified"])
        self.assertFalse(packet["approved_for_queue"])
        self.assertFalse(packet["meta_posted"])


    def test_later_single_count_with_explicit_time_gets_one_evidence_attempt(self):
        drafts = []
        for i in range(12):
            drafts.append({"notice_id": "a" + str(i), "status": "unreviewed",
                           "official_url_for_private_review":
                               self.url + "/" + str(i),
                           "official_detail_fields_for_review": {
                               "recrutNope": "1" if i in (8, 10, 11) else "2"},
                           "application_evidence_for_review":
                               "2026.12.03. 16:00" if i in (9, 10, 11)
                               else "2026.12.03."})
        packet = build_packet({"status": "review_required", "approved_for_queue": False,
                               "drafts": drafts},
                              fetch=lambda url: {"url": url, "sha256": "a" * 64})
        self.assertEqual([x["notice_id"] for x in packet["records"]],
                         ["a" + str(i) for i in (0, 1, 2, 3, 4, 5, 6, 10)])
        self.assertEqual(packet["checked"], 8)
        self.assertFalse(packet["automatic_approval"])
        self.assertFalse(packet["approved_for_queue"])
        self.assertFalse(packet["meta_posted"])
        self.assertTrue(all(x["publisher_validate_entry"] == "not_run"
                            for x in packet["records"]))

    def test_pinned_mudeungsan_gets_bounded_evidence_slot_and_board_receipt(self):
        from scripts.threads_official_review_pack import CANONICAL_REVIEW_BOARDS
        pin = CANONICAL_REVIEW_BOARDS["a307417"]
        drafts = [{"notice_id": str(i), "status": "unreviewed",
                   "official_url_for_private_review": self.url + "/" + str(i)}
                  for i in range(12)]
        drafts[9].update(notice_id="a307417",
                         source_post_sha256=pin["source_post_sha256"],
                         source_detail_sha256=pin["source_detail_sha256"])
        bundle = {"status": "review_required", "approved_for_queue": False, "drafts": drafts}
        def fetch(url):
            return {"url": url, "sha256": "a" * 64, "visible_text_excerpt": pin["expected_notice"]}
        result = build_packet(bundle, fetch=fetch)
        self.assertEqual(result["checked"], 8)
        self.assertEqual(result["attempted"], 8)
        self.assertEqual([r["notice_id"] for r in result["records"]],
                         [str(i) for i in range(7)] + ["a307417"])
        receipt = result["records"][-1]["employer_recruitment_board_receipt"]
        self.assertEqual(receipt["status"], "board_bytes_fetched_for_independent_review")
        self.assertFalse(receipt["correction_absence_verified"])
        self.assertFalse(result["approved_for_queue"])
        self.assertFalse(result["meta_posted"])
        drafts[9]["source_detail_sha256"] = "0" * 64
        changed = build_packet(bundle, fetch=fetch)
        self.assertNotIn("a307417", [r["notice_id"] for r in changed["records"]])


    def test_reviewed_reserves_receive_bounded_receipt_budget(self):
        drafts = [{"notice_id": str(i), "status": "unreviewed",
                   "official_url_for_private_review": self.url + "/" + str(i)}
                  for i in range(12)]
        reserves = [
            ("a307341", "c315c9528c5554af2aae756635cd1a4965c517b65327b33275ea89c5090b8ed1",
             "c02eec954ea0bf8e0f717e93ac38b642bebd327418f197524e68216a2366b04e"),
            ("a307565", "02d55f5750529edc0a6fe6168a3a80a1faed33e74d0542a5fbb446d4cbd82266",
             "917ffe360f9483cc8ce4ec311d26d97237b53d72cc1e0e0aa3dcf89b906b0c1a"),
            ("a307324", "7530ce3170ed0d8021a7ef3ba46f74de4b1939faa67263eafaebc355cbb65a09",
             "5b28db9b04ef423a744d46188ca8b516635dfc6d67c37220e27da89a34088dc7"),
        ]
        later = [{"notice_id": nid, "status": "unreviewed",
                  "source_post_sha256": post, "source_detail_sha256": detail,
                  "official_url_for_private_review": self.url + "/" + nid}
                 for nid, post, detail in reserves]
        bundle = {"status": "review_required", "approved_for_queue": False,
                  "drafts": drafts + later[:2], "official_source_alternatives": later[2:]}
        def fetch(url):
            return {"url": url, "sha256": "a" * 64}
        result = build_packet(bundle, fetch=fetch)
        self.assertEqual([r["notice_id"] for r in result["records"]],
                         [str(i) for i in range(5)] + [r[0] for r in reserves])
        self.assertEqual(result["attempted"], 8)
        self.assertEqual(result["checked"], 8)
        self.assertFalse(result["approved_for_queue"])
        self.assertFalse(result["automatic_approval"])
        self.assertFalse(result["meta_posted"])
        self.assertTrue(all(r["publisher_validate_entry"] == "not_run"
                            for r in result["records"]))
        later[0]["source_detail_sha256"] = "0" * 64
        changed = build_packet(bundle, fetch=fetch)
        self.assertNotIn("a307341", [r["notice_id"] for r in changed["records"]])
        self.assertEqual(changed["attempted"], 8)
        small = build_packet(bundle, fetch=fetch, limit=1, max_attempts=1)
        self.assertEqual([r["notice_id"] for r in small["records"]], ["0"])


if __name__ == "__main__":
    unittest.main()
