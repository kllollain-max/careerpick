"""Fresh official API comparison and deferral before any transport call."""
import copy
import unittest
from unittest.mock import patch

from scripts import cleaneye_push_preflight as preflight
from scripts import push_official_preflight as router
from scripts.detect_new_job_alerts import compact
from test_alert_cleaneye_detection import NOW, cleaneye_job


class CleaneyePreflightTests(unittest.TestCase):
    def test_unchanged_current_official_post_allowed(self):
        job = cleaneye_job()
        self.assertEqual(preflight.verify(compact(job), NOW, fetcher=lambda *_: job),
                         {"allowed": True, "definitive": True, "reason": "cleaneye_open_verified"})

    def test_source_changes_require_refresh_before_sending(self):
        for key, value in (("emp", ["일반정규직"]), ("region", "서울"),
                           ("text", "changed matching text"), ("due", "2026-11-13T23:59:59+09:00")):
            with self.subTest(key=key):
                job = cleaneye_job()
                prior = compact(job)
                prior[key] = value
                result = preflight.verify(prior, NOW, fetcher=lambda *_: job)
                self.assertFalse(result["allowed"])
                self.assertFalse(result["definitive"])

    def test_explicit_closed_or_cancelled_is_definitive(self):
        for state in ("cancelled", "expired"):
            with self.subTest(state=state):
                job = cleaneye_job()
                result = preflight.verify(compact(job), NOW,
                                          fetcher=lambda *_: dict(job, receptionState=state))
                self.assertFalse(result["allowed"])
                self.assertTrue(result["definitive"])

    def test_unknown_response_stays_pending_without_leaking_exception(self):
        def failed(*_):
            raise RuntimeError("secret fixture request should not be printed")
        self.assertEqual(preflight.verify(compact(cleaneye_job()), NOW, fetcher=failed),
                         {"allowed": False, "definitive": False, "reason": "cleaneye_official_unverified"})

    def test_date_only_deadline_day_is_not_promoted_as_open(self):
        job = cleaneye_job()
        at_deadline = NOW.replace(day=12)
        result = preflight.verify(compact(job), at_deadline, fetcher=lambda *_: job)
        self.assertFalse(result["allowed"])
        self.assertFalse(result["definitive"])

    def test_verified_official_region_mapping_used_without_workplace_inference(self):
        calls = []
        class Client:
            def __init__(self, key): pass
            def collect_region_codes(self, *, ac_year):
                calls.append(("codes", ac_year))
                return {"official-code": "서울특별시"}
            def list_region(self, code):
                calls.append(("region", code))
                return {"totalCount": 1, "result": [{"NO": "9001", "ENT_NAME": "테스트공단",
                    "ENT_TITLE": "기간제 직원 채용 공고", "SIDO_CD": "서울특별시",
                    "URL": "https://job.cleaneye.go.kr/user/ypCareersData.do?idx=9001",
                    "STATUS": "모집중", "JOB_TYPE": "기간제", "PUB_DATE": "2026-11-06",
                    "PUB_END_DATE": "2026-11-12", "EMPLOY_NUM": "2"}]}
        result = preflight.fetch_current(compact(cleaneye_job()), NOW, client_factory=Client)
        self.assertEqual(calls, [("codes", 2026), ("region", "official-code")])
        self.assertEqual(result["region"], "")
        self.assertEqual(result["sourceRegion"], "서울특별시")

    def test_router_uses_cleaneye_api_and_never_alio_page_for_cleaneye(self):
        result = {"allowed": False, "definitive": False, "reason": "fixture"}
        with patch.object(preflight, "verify", return_value=result) as check:
            self.assertEqual(router.verify(compact(cleaneye_job()), NOW,
                             fetcher=lambda *_: self.fail("ALIO should not run")), result)
            check.assert_called_once()
