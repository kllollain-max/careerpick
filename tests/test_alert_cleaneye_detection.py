"""Source onboarding and failure regressions; no API or private-store access."""
import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scripts import detect_new_job_alerts as detector
from scripts.collect_cleaneye import normalize

NOW = datetime(2026, 11, 7, 14, 0, tzinfo=detector.KST)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


def cleaneye_job(number="9001"):
    return normalize({"NO": number, "ENT_NAME": "테스트공단", "ENT_TITLE": "기간제 직원 채용 공고",
                      "URL": "https://job.cleaneye.go.kr/user/ypCareersData.do?idx=" + number,
                      "SIDO_CD": "서울특별시", "STATUS": "모집중", "JOB_TYPE": "기간제",
                      "PUB_DATE": "2026-11-06", "PUB_END_DATE": "2026-11-12", "EMPLOY_NUM": "2"}, NOW)


class CleaneyeDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data, self.state, self.report = [self.root / name for name in
                                            ("alio.json", "state.json", "report.json")]
        self.state.write_text(json.dumps({"ids": ["a1"]}))
        self.alio = [{"id": "a1", "alio": True, "type": "j", "title": "채용",
                      "due": "2026-11-12T18:00:00+09:00"}]
        self.data.write_text(json.dumps({"posts": self.alio}))
        self.write_feed([cleaneye_job()])

    def write_feed(self, posts, **overrides):
        feed = {"source": "cleaneye", "collectionStatus": "verified",
                "updated": NOW.isoformat(), "posts": posts}
        feed.update(overrides)
        (self.root / "cleaneye.json").write_text(json.dumps(feed))

    def run_detector(self, persister=None):
        env = {"CP_UPDATE_ALERT_STATE": "1", "CP_ALERT_REPORT": str(self.report)}
        if persister:
            env["CP_PERSIST_ALERT_BACKLOG"] = "1"
        with patch.object(detector, "DATA", self.data), patch.object(detector, "STATE", self.state), \
                patch.object(detector, "datetime", Clock), patch.dict(os.environ, env, clear=True), \
                redirect_stdout(io.StringIO()):
            detector.main(backlog_persister=persister)
        return json.loads(self.report.read_text())

    def test_source_onboarding_does_not_broadcast_history_or_suppress_new_alio(self):
        self.alio.append(dict(self.alio[0], id="a2"))
        self.data.write_text(json.dumps({"posts": self.alio}))
        self.write_feed([cleaneye_job("9001"), cleaneye_job("9002")])
        report = self.run_detector()
        self.assertEqual([job["id"] for job in report["new_jobs"]], ["a2"])
        self.assertTrue(report["source_bootstrap"]["cleaneye"])
        baseline = json.loads(self.state.read_text())
        self.assertEqual(baseline["ids"], ["a1", "a2", "cleaneye-9001", "cleaneye-9002"])
        self.assertEqual(baseline["initialized_sources"], ["alio", "cleaneye"])

    def test_later_new_job_detected_once_with_official_metadata(self):
        self.run_detector()
        self.write_feed([cleaneye_job("9001"), cleaneye_job("9002")])
        report = self.run_detector()
        self.assertEqual([job["id"] for job in report["new_jobs"]], ["cleaneye-9002"])
        job = report["new_jobs"][0]
        self.assertEqual(job["region"], "")
        self.assertEqual(job["sourceRegion"], "서울특별시")
        self.assertFalse(job["dueHasTime"])
        self.assertEqual(job["src"], job["url"])
        self.assertEqual(job["cleaneyeDetail"]["접수마감일 원문"], "2026-11-12")
        self.assertEqual(self.run_detector()["new_count"], 0)

    def test_stale_feed_does_not_initialize_source_or_erase_seen_ids(self):
        self.write_feed([cleaneye_job()], updated="2026-11-05T13:00:00+09:00")
        report = self.run_detector()
        self.assertEqual(report["source_status"]["cleaneye"], "unverified")
        self.assertEqual(json.loads(self.state.read_text())["ids"], ["a1"])
        self.write_feed([cleaneye_job()])
        self.assertEqual(self.run_detector()["new_count"], 0)
        (self.root / "cleaneye.json").unlink()
        self.run_detector()
        self.assertIn("cleaneye-9001", json.loads(self.state.read_text())["ids"])
        self.write_feed([cleaneye_job()])
        self.assertEqual(self.run_detector()["new_count"], 0)

    def test_duplicate_identity_does_not_advance_source_baseline(self):
        self.write_feed([cleaneye_job(), cleaneye_job()])
        self.assertEqual(self.run_detector()["source_status"]["cleaneye"], "unverified")
        self.assertNotIn("cleaneye", json.loads(self.state.read_text())["initialized_sources"])

    def test_empty_feed_does_not_bootstrap_then_alert_restored_history(self):
        self.write_feed([])
        self.assertEqual(self.run_detector()["source_status"]["cleaneye"], "unverified")
        self.write_feed([cleaneye_job()])
        self.assertEqual(self.run_detector()["new_count"], 0)

    def test_unverified_or_result_notice_never_enters_candidates(self):
        self.run_detector()
        pending = cleaneye_job("9002")
        pending["receptionState"] = "verification_pending"
        result = cleaneye_job("9003")
        result["title"] = result["cleaneyeDetail"]["채용제목"] = "직원 채용 필기시험 안내"
        self.write_feed([cleaneye_job(), pending, result])
        self.assertEqual(self.run_detector()["new_count"], 0)

    def test_failed_private_handoff_preserves_baseline_for_retry(self):
        self.run_detector()
        original = self.state.read_bytes()
        self.write_feed([cleaneye_job(), cleaneye_job("9002")])
        def failed(report):
            self.assertEqual(report["new_jobs"][0]["id"], "cleaneye-9002")
            raise RuntimeError("fixture storage unavailable")
        with self.assertRaises(RuntimeError):
            self.run_detector(failed)
        self.assertEqual(self.state.read_bytes(), original)

