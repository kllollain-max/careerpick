import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import urllib.request

from scripts.threads_source_verification import inspect_bundle, attach, verified_time, PROOF, SafeRedirect
from scripts.cleaneye_source_adapter import validate_cleaneye_feed, SourceValidationError


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 11, 16, 0, tzinfo=timezone.utc)
        self.old = self.now - timedelta(hours=30)
        self.recent = self.now - timedelta(hours=2)
        self.feed = {'source': 'cleaneye', 'collectionStatus': 'verified',
            'updated': self.old.isoformat(), 'posts': [{'cleaneye': True, 'type': 'j',
            'source': '클린아이 잡플러스', 'sourceMissing': False, 'id': 'cleaneye-7',
            'cleaneyeDetail': {'공고 고유번호': '7'}}]}
        for name, value in [('cleaneye.json', self.feed), ('alio.json', {'posts': []}),
                            ('alio-detail.json', {})]:
            (self.root / name).write_text(json.dumps(value))
        self.hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}
        self.run = {'id': 7, 'head_sha': 'a'*40, 'repository': {'id': 8,
            'full_name': 'kllollain-max/careerpick'}, 'path': '.github/workflows/operations.yml',
            'event': 'schedule', 'head_branch': 'main', 'status': 'completed', 'conclusion': 'success',
            'run_started_at': self.recent.isoformat(), 'updated_at': (self.recent+timedelta(minutes=5)).isoformat()}
        self.artifact = {'id': 9, 'name': 'operation-7', 'expired': False,
            'created_at': (self.recent+timedelta(minutes=4)).isoformat(),
            'workflow_run': {'id': 7, 'head_sha': 'a'*40, 'head_branch': 'main',
            'repository_id': 8, 'head_repository_id': 8}}
        self.report = {'trigger': 'schedule', 'job_status': 'success',
            'run_url': 'https://github.com/kllollain-max/careerpick/actions/runs/7',
            'source': 'alio', 'collection': 'success', 'validation': 'success',
            'status': 'unchanged', 'changed': False, 'originals_preserved': True,
            'source_hashes': self.hashes, 'verified_at': self.recent.isoformat(),
            'overall': 'partial_or_failed'}
        self.clean = {'source': 'cleaneye', 'status': 'unchanged', 'changed': False,
            'originals_preserved': True, 'authentication_verified': True, 'complete_collection': True,
            'region_code_lookup_verified': True, 'successful_responses': {'list': 17},
            'candidate_sha256': self.hashes['cleaneye.json'], 'source_sha256': self.hashes,
            'started_at': self.recent.isoformat()}

    def bundle(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            z.writestr('operations-output/previous-head.txt', self.run['head_sha'])
            z.writestr('operations-output/report.json', json.dumps(self.report))
            z.writestr('cleaneye-operation-output/report.json', json.dumps(self.clean))
        artifact = deepcopy(self.artifact)
        artifact['digest'] = 'sha256:'+hashlib.sha256(b.getvalue()).hexdigest()
        return {'run': deepcopy(self.run), 'artifact': artifact,
                'zip_base64': base64.b64encode(b.getvalue()).decode()}

    def test_real_verification_does_not_change_content_timestamp_or_files(self):
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        with self.assertRaises(SourceValidationError):
            validate_cleaneye_feed(self.feed, self.now)
        (self.root/PROOF).write_text(json.dumps(self.bundle()))
        source = attach(self.root, {'_cleaneye':deepcopy(self.feed)}, self.now)
        feed = source['_cleaneye']
        self.assertTrue(validate_cleaneye_feed(feed, self.now, scheduled=self.now+timedelta(hours=8)))
        self.assertEqual(feed['updated'], self.old.isoformat())
        for name, data in before.items(): self.assertEqual((self.root/name).read_bytes(), data)

    def test_actual_24h_window_still_applies_to_future_slot(self):
        (self.root/PROOF).write_text(json.dumps(self.bundle()))
        feed = attach(self.root, {'_cleaneye':deepcopy(self.feed)}, self.now)['_cleaneye']
        with self.assertRaises(SourceValidationError):
            validate_cleaneye_feed(feed, self.now, scheduled=self.now+timedelta(hours=23))

    def test_stricter_freshness_limit_is_preserved(self):
        (self.root/PROOF).write_text(json.dumps(self.bundle()))
        feed = attach(self.root, {'_cleaneye':deepcopy(self.feed)}, self.now)['_cleaneye']
        with self.assertRaises(SourceValidationError):
            validate_cleaneye_feed(feed, self.now, scheduled=self.now+timedelta(hours=8), max_age_hours=6)

    def test_artifact_redirect_never_forwards_github_token(self):
        req = urllib.request.Request('https://api.github.com/repos/kllollain-max/careerpick/actions/artifacts/9/zip', headers={'Authorization':'Bearer test-only'})
        handler = SafeRedirect()
        redirected = handler.redirect_request(req, None, 302, '', {}, 'https://example.blob.core.windows.net/archive?test=1')
        self.assertIsNone(redirected.get_header('Authorization'))
        for url in ['http://example.blob.core.windows.net/archive', 'https://attacker.invalid/archive']:
            with self.assertRaises(ValueError): handler.redirect_request(req, None, 302, '', {}, url)

    def test_changed_snapshot_cannot_borrow_old_receipt(self):
        b = self.bundle()
        (self.root/'cleaneye.json').write_text('{}')
        self.assertNotIn('cleaneye', inspect_bundle(b, self.root, self.now))

    def test_in_memory_changes_invalidate_proof(self):
        (self.root/PROOF).write_text(json.dumps(self.bundle()))
        feed = attach(self.root, {'_cleaneye':deepcopy(self.feed)}, self.now)['_cleaneye']
        feed['posts'][0]['sourceMissing'] = True
        with self.assertRaises(ValueError): verified_time(feed, self.now, self.now)

    def test_bad_digest_failed_run_fork_and_future_metadata_rejected(self):
        for key, value in [('event', 'pull_request'), ('conclusion', 'failure'), ('head_branch', 'feature')]:
            b = self.bundle(); b['run'][key] = value
            with self.assertRaises(ValueError): inspect_bundle(b, self.root, self.now)
        b = self.bundle(); b['artifact']['digest'] = 'sha256:'+'0'*64
        with self.assertRaises(ValueError): inspect_bundle(b, self.root, self.now)
        b = self.bundle(); b['artifact']['workflow_run']['head_repository_id'] = 99
        with self.assertRaises(ValueError): inspect_bundle(b, self.root, self.now)
        b = self.bundle(); b['run']['updated_at'] = (self.now+timedelta(minutes=1)).isoformat()
        with self.assertRaises(ValueError): inspect_bundle(b, self.root, self.now)

    def test_partial_unrelated_source_does_not_approve_failed_cleaneye(self):
        self.clean['complete_collection'] = False
        stamps = inspect_bundle(self.bundle(), self.root, self.now)
        self.assertIn('alio', stamps)
        self.assertNotIn('cleaneye', stamps)

    def test_missing_or_invalid_proof_leaves_strict_original_gate(self):
        for content in [None, '{}', 'invalid']:
            if content is not None: (self.root/PROOF).write_text(content)
            feed = attach(self.root, {'_cleaneye':deepcopy(self.feed)}, self.now)['_cleaneye']
            with self.assertRaises(SourceValidationError): validate_cleaneye_feed(feed, self.now)


if __name__ == '__main__': unittest.main()
