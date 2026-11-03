"""Regression tests for ALIO alert detection, using isolated temporary fixtures."""
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from scripts import detect_new_job_alerts as detector

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "detect_new_job_alerts.py"
KST = ZoneInfo("Asia/Seoul")

class AlertDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "scripts").mkdir()
        (root / "scripts" / SOURCE.name).write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
        self.root = root
        self.report = root / "report.json"

    def run_detector(self, posts):
        (self.root / "alio.json").write_text(json.dumps({"posts": posts}), encoding="utf-8")
        env = dict(os.environ, CP_UPDATE_ALERT_STATE="1", CP_ALERT_REPORT=str(self.report))
        subprocess.run([sys.executable, str(self.root / "scripts" / SOURCE.name)], env=env, check=True, capture_output=True)
        return json.loads(self.report.read_text(encoding="utf-8"))

    def job(self, job_id, due):
        return {"id": job_id, "type": "j", "alio": True, "org": "테스트 기관",
                "title": "테스트 채용", "due": due.isoformat(), "region": "서울"}

    def test_first_run_does_not_mass_alert_existing_jobs(self):
        due = datetime.now(KST) + timedelta(days=5)
        result = self.run_detector([self.job("1", due)])
        self.assertTrue(result["initial_run"])
        self.assertEqual(result["new_count"], 0)

    def test_only_new_jobs_alert_once(self):
        due = datetime.now(KST) + timedelta(days=5)
        a, b = self.job("1", due), self.job("2", due)
        self.run_detector([a])
        self.assertEqual(self.run_detector([a, b])["new_count"], 1)
        self.assertEqual(self.run_detector([a, b])["new_count"], 0)

    def test_empty_snapshot_preserves_baseline_and_never_realerts(self):
        due = datetime.now(KST) + timedelta(days=5)
        a, b = self.job("1", due), self.job("2", due)
        self.run_detector([a])
        state_path = self.root / ".notification-state.json"
        original = state_path.read_bytes()
        (self.root / "alio.json").write_text(
            json.dumps({"posts": []}), encoding="utf-8")
        env = dict(os.environ, CP_UPDATE_ALERT_STATE="1",
                   CP_ALERT_REPORT=str(self.report))
        run = subprocess.run(
            [sys.executable, str(self.root / "scripts" / SOURCE.name)],
            env=env, capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(state_path.read_bytes(), original)
        self.assertEqual(self.run_detector([a, b])["new_count"], 1)

    def test_malformed_snapshot_does_not_change_baseline(self):
        due = datetime.now(KST) + timedelta(days=5)
        self.run_detector([self.job("1", due)])
        state_path = self.root / ".notification-state.json"
        original = state_path.read_bytes()
        for payload in ([], {"posts": None}, {"posts": {}}, {"missing": []}):
            with self.subTest(payload=payload):
                (self.root / "alio.json").write_text(
                    json.dumps(payload), encoding="utf-8")
                env = dict(os.environ, CP_UPDATE_ALERT_STATE="1",
                           CP_ALERT_REPORT=str(self.report))
                run = subprocess.run(
                    [sys.executable, str(self.root / "scripts" / SOURCE.name)],
                    env=env, capture_output=True, text=True)
                self.assertNotEqual(run.returncode, 0)
                self.assertEqual(state_path.read_bytes(), original)

    def test_invalid_previous_ids_preserves_state(self):
        due = datetime.now(KST) + timedelta(days=5)
        self.run_detector([self.job("1", due)])
        path = self.root / ".notification-state.json"
        path.write_text('{"ids": null}', encoding="utf-8")
        original = path.read_bytes()
        (self.root / "alio.json").write_text(
            json.dumps({"posts": [self.job("1", due)]}), encoding="utf-8")
        env = dict(os.environ, CP_UPDATE_ALERT_STATE="1",
                   CP_ALERT_REPORT=str(self.report))
        result = subprocess.run(
            [sys.executable, str(self.root / "scripts" / SOURCE.name)],
            env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_bytes(), original)

    def test_deadline_d1_candidates_repeat_without_marking_delivery(self):
        tomorrow = datetime.now(KST).date() + timedelta(days=1)
        due = datetime.combine(tomorrow, datetime.min.time(), tzinfo=KST) + timedelta(hours=23)
        a = self.job("1", due)
        self.assertEqual(self.run_detector([a])["deadline_d1_count"], 1)
        self.assertEqual(self.run_detector([a])["deadline_d1_count"], 1)
        state = json.loads((self.root / ".notification-state.json").read_text(encoding="utf-8"))
        self.assertNotIn("deadline_alerted", state)


class AlertBacklogHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.data, self.state, self.report = root/'alio.json', root/'state.json', root/'report.json'
        self.state.write_text(json.dumps({'ids':['a1']}))
        self.original = self.state.read_bytes()
        due = (datetime.now(detector.KST) + timedelta(days=5)).isoformat()
        self.posts = [{'id':k,'type':'j','alio':True,'title':'채용','due':due} for k in ('a1','a2')]
        self.data.write_text(json.dumps({'posts':self.posts}))
        self.env = {'CP_UPDATE_ALERT_STATE':'1','CP_PERSIST_ALERT_BACKLOG':'1','CP_ALERT_REPORT':str(self.report)}
        self.backlog = {}

    def persist(self, report):
        self.assertEqual(self.state.read_bytes(), self.original)
        for job in report['new_jobs']:
            self.backlog[job['id']] = copy.deepcopy(job)
        return {'verified':True,'fresh_valid_candidates':len(report['new_jobs']),
                'saved_records':len(self.backlog),'sent':0}

    def run_detector(self, persister):
        with patch.object(detector,'DATA',self.data), patch.object(detector,'STATE',self.state), \
             patch.dict(os.environ,self.env,clear=True), redirect_stdout(io.StringIO()):
            detector.main(backlog_persister=persister)

    def test_save_before_baseline_and_later_sender_can_read_backlog(self):
        self.run_detector(self.persist)
        self.assertEqual(json.loads(self.state.read_text())['ids'],['a1','a2'])
        self.assertEqual(set(self.backlog),{'a2'})
        self.original = self.state.read_bytes()
        self.run_detector(self.persist)
        self.assertEqual(json.loads(self.report.read_text())['new_count'],0)
        self.assertEqual(set(self.backlog),{'a2'})

    def test_failed_storage_keeps_baseline_for_retry(self):
        def failure(report):
            raise RuntimeError('storage unavailable')
        with self.assertRaises(RuntimeError):
            self.run_detector(failure)
        self.assertEqual(self.state.read_bytes(),self.original)
        self.assertFalse(self.report.exists())
        self.run_detector(self.persist)
        self.assertEqual(set(self.backlog),{'a2'})

    def test_readback_mismatch_keeps_baseline(self):
        def mismatch(report):
            self.backlog['a2'] = report['new_jobs'][0]
            raise RuntimeError('readback mismatch')
        with self.assertRaises(RuntimeError):
            self.run_detector(mismatch)
        self.assertEqual(self.state.read_bytes(),self.original)
        self.run_detector(self.persist)
        self.assertEqual(len(self.backlog),1)

    def test_invalid_handoff_never_advances(self):
        for result in (None,{}, {'verified':False,'sent':0},
                       {'verified':True,'sent':1,'fresh_valid_candidates':1,'saved_records':1},
                       {'verified':True,'sent':0,'fresh_valid_candidates':True,'saved_records':1}):
            with self.subTest(result=result), self.assertRaises(RuntimeError):
                self.run_detector(lambda report: result)
            self.assertEqual(self.state.read_bytes(),self.original)

    def test_first_run_does_not_backfill_or_touch_private_store(self):
        self.state.unlink()
        self.run_detector(lambda report: self.fail('no historical backfill'))
        report = json.loads(self.report.read_text())
        self.assertTrue(report['initial_run'])
        self.assertEqual(report['new_jobs'],[])
        self.assertEqual(report['backlog_handoff']['status'],'bootstrap_no_candidates')

    def test_no_flag_keeps_original_offline_behavior(self):
        self.env.pop('CP_PERSIST_ALERT_BACKLOG')
        self.run_detector(lambda report: self.fail('private storage not enabled'))
        self.assertNotIn('backlog_handoff',json.loads(self.report.read_text()))
        self.assertEqual(json.loads(self.state.read_text())['ids'],['a1','a2'])

    def test_no_baseline_update_flag_preserves_state(self):
        self.env.pop('CP_UPDATE_ALERT_STATE')
        self.run_detector(self.persist)
        self.assertEqual(self.state.read_bytes(),self.original)
        self.assertEqual(set(self.backlog),{'a2'})

    def test_atomic_replace_failure_keeps_original_and_cleans_temp(self):
        with patch.object(detector.os,'replace',side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                self.run_detector(self.persist)
        self.assertEqual(self.state.read_bytes(),self.original)
        self.assertEqual(list(self.state.parent.glob('.notification-*')),[])
        self.run_detector(self.persist)
        self.assertEqual(len(self.backlog),1)

    def test_expired_job_does_not_enter_backlog(self):
        self.posts[1]['due'] = (datetime.now(detector.KST)-timedelta(days=1)).isoformat()
        self.data.write_text(json.dumps({'posts':self.posts}))
        self.run_detector(self.persist)
        self.assertEqual(self.backlog,{})

    def test_empty_snapshot_does_not_call_storage_or_advance(self):
        self.data.write_text(json.dumps({'posts':[]}))
        with self.assertRaises(RuntimeError):
            self.run_detector(lambda report: self.fail('invalid snapshot'))
        self.assertEqual(self.state.read_bytes(),self.original)


if __name__ == "__main__":
    unittest.main()
