"""Regressions for incomplete/invalid collection and all-or-nothing snapshots."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import alio

NOW = datetime(2026, 11, 3, 14, 0, tzinfo=alio.KST)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


def notice(sn, **fields):
    return {'recrutPblntSn': str(sn), 'recrutPbancTtl': '채용 공고', 'instNm': '기관',
            'pbancBgngYmd': '20261101', 'pbancEndYmd': '20261130', **fields}


def page(total, *rows):
    return {'totalCount': total, 'result': list(rows)}


class CollectionGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.out, self.detail = self.root / 'alio.json', self.root / 'alio-detail.json'
        self.out.write_text('{"updated":"prior", "posts":[{"id":"a900"}]}')
        self.detail.write_text('{"a900":{"recrutPblntSn":"900"}}')
        self.before = (self.out.read_bytes(), self.detail.read_bytes())

    def tearDown(self):
        self.directory.cleanup()

    def run_collection(self, pages, **overrides):
        self.log = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(alio, 'OUT', self.out))
            stack.enter_context(patch.object(alio, 'DETAIL', self.detail))
            stack.enter_context(patch.object(alio, 'PER_PAGE', 2))
            stack.enter_context(patch.object(alio, 'datetime', Clock))
            stack.enter_context(patch.dict(os.environ, {'ALIO_KEY': 'SECRET_NEVER_LOG'}))
            self.mock_call = stack.enter_context(patch.object(alio, 'call', side_effect=pages))
            for name, value in overrides.items():
                stack.enter_context(patch.object(alio, name, value))
            stack.enter_context(contextlib.redirect_stdout(self.log))
            return alio.main()

    def assert_preserved(self):
        self.assertEqual(self.before, (self.out.read_bytes(), self.detail.read_bytes()))

    def test_duplicate_later_page_preserves_both_snapshots(self):
        result = self.run_collection([page(3, notice(1), notice(2)), page(3, notice(2))])
        self.assertIsNone(result)
        self.assertEqual(self.mock_call.call_count, 2)
        self.assert_preserved()

    def test_changed_total_cannot_confirm_a_moving_collection(self):
        result = self.run_collection([page(3, notice(1), notice(2)), page(4, notice(3), notice(4))])
        self.assertIsNone(result)
        self.assert_preserved()

    def test_missing_short_extra_or_oversized_page_cannot_overwrite(self):
        samples = [
            [page(3, notice(1))],
            [page(3, notice(1), notice(2)), page(3)],
            [page(3, notice(1), notice(2)), page(3, notice(3), notice(4))],
            [page(3, notice(1), notice(2), notice(3))],
        ]
        for pages in samples:
            with self.subTest(pages=pages):
                self.assertIsNone(self.run_collection(pages))
                self.assert_preserved()

    def test_invalid_totals_and_official_ids_fail_closed(self):
        for total in (None, True, -1, 1.5, '1.5'):
            with self.subTest(total=total):
                self.assertIsNone(self.run_collection([page(total, notice(1))]))
                self.assert_preserved()
        for identity in (None, True, 0, '01', '-1', 'x', '١'):
            with self.subTest(identity=identity):
                self.assertIsNone(self.run_collection([page(1, notice(1, recrutPblntSn=identity))]))
                self.assert_preserved()

    def test_malformed_notice_is_not_silently_dropped_even_when_expired(self):
        samples = [
            notice(2, recrutPbancTtl=''), notice(2, instNm=''),
            notice(2, pbancEndYmd='invalid'), notice(2, pbancBgngYmd='invalid'),
            notice(2, pbancEndYmd='20200101', recrutPbancTtl=''),
        ]
        for bad in samples:
            with self.subTest(fields=bad):
                self.assertIsNone(self.run_collection([page(2, notice(1), bad)]))
                self.assert_preserved()

    def test_valid_expired_notice_is_filtered_without_discarding_valid_active_notice(self):
        result = self.run_collection([page(2, notice(1), notice(2, pbancEndYmd='20261030'))])
        self.assertEqual(len(result), 2)
        self.assertEqual([p['id'] for p in json.loads(self.out.read_text())['posts']], ['a1'])
        self.assertEqual(set(json.loads(self.detail.read_text())), {'a1'})

    def test_empty_active_collection_preserves_existing_pair(self):
        self.assertIsNone(self.run_collection([page(1, notice(1, pbancEndYmd='20261030'))]))
        self.assert_preserved()

    def test_conversion_or_detail_failure_never_logs_response_text(self):
        def broken(*args):
            raise RuntimeError('SECRET_NEVER_LOG RAW_RESPONSE')
        for target in ('convert', 'detail_of'):
            with self.subTest(target=target):
                self.assertIsNone(self.run_collection([page(1, notice(1))], **{target: broken}))
                self.assertNotIn('SECRET_NEVER_LOG', self.log.getvalue())
                self.assertNotIn('RAW_RESPONSE', self.log.getvalue())
                self.assert_preserved()

    def test_unexpected_missing_conversion_or_wrong_detail_identity_aborts_batch(self):
        for overrides in ({'convert': lambda *args: None},
                          {'detail_of': lambda *args: {'recrutPblntSn': '999'}}):
            self.assertIsNone(self.run_collection([page(1, notice(1))], **overrides))
            self.assert_preserved()

    def test_second_file_replacement_failure_restores_both_originals(self):
        original_replace = os.replace
        replacements = 0
        def fail_second(source, destination):
            nonlocal replacements
            replacements += 1
            if replacements == 2:
                raise OSError('SECRET_NEVER_LOG')
            return original_replace(source, destination)
        with patch('alio.os.replace', side_effect=fail_second):
            self.assertIsNone(self.run_collection([page(1, notice(1))]))
        self.assert_preserved()
        self.assertNotIn('SECRET_NEVER_LOG', self.log.getvalue())
        self.assertEqual(set(self.root.iterdir()), {self.out, self.detail})


if __name__ == '__main__':
    unittest.main()
