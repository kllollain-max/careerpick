import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.threads_writer_queue import _application_period, QueueValidationError


class DeadlineTimezoneTests(unittest.TestCase):
    def review(self, end='2026-11-30T23:59:59+00:00', evidence=None):
        evidence = evidence or '2026-10-06 ~ 2026-11-30 23:59:59 UTC'
        period = dict(start='2026-10-06', start_date_only=True, end=end,
                      date_only=False, source_ref='official', evidence=evidence)
        return {'application_period': period}, [{'ref': 'official', 'excerpt': evidence}]

    def check(self, end='2026-11-30T23:59:59+00:00', evidence=None, now=None):
        review, refs = self.review(end, evidence)
        now = now or datetime(2026, 11, 15, 17, tzinfo=ZoneInfo('Asia/Seoul'))
        return _application_period(review, refs, {}, now, now)

    def test_utc_deadline_rolls_to_next_kst_day(self):
        day, _, seconds = self.check()
        self.assertEqual(day, '2026-12-01')
        self.assertTrue(seconds)

    def test_json_ld_offset_is_explicit_timezone_evidence(self):
        day, _, _ = self.check(evidence='datePosted date: 2026-10-06; validThrough: 2026-11-30T23:59:59+00:00')
        self.assertEqual(day, '2026-12-01')

    def test_wrong_utc_clock_rejected(self):
        with self.assertRaisesRegex(QueueValidationError, 'END_TIME_EVIDENCE_MISMATCH'):
            self.check(end='2026-11-30T22:59:59+00:00')

    def test_iso_timezone_offset_is_not_a_midnight_clock(self):
        with self.assertRaisesRegex(QueueValidationError, 'END_TIME_EVIDENCE_MISMATCH'):
            self.check(end='2026-11-30T00:00:00+00:00', evidence='2026-10-06 ~ 2026-11-30T23:59:59+00:00')

    def test_wrong_calendar_day_rejected(self):
        with self.assertRaisesRegex(QueueValidationError, 'END_EVIDENCE_MISMATCH'):
            self.check(end='2026-11-29T23:59:59+00:00')

    def test_non_kst_zone_must_be_explicit(self):
        with self.assertRaisesRegex(QueueValidationError, 'TIMEZONE_EVIDENCE_REQUIRED'):
            self.check(evidence='2026-10-06 ~ 2026-11-30 23:59:59')

    def test_offset_may_not_be_relabelled_kst(self):
        with self.assertRaisesRegex(QueueValidationError, 'END_EVIDENCE_MISMATCH'):
            self.check(end='2026-12-01T08:59:59+09:00')

    def test_normal_kst_evidence_unchanged(self):
        day, _, seconds = self.check(end='2026-11-30T17:00:00+09:00', evidence='2026-10-06 ~ 2026-11-30 17:00')
        self.assertEqual(day, '2026-11-30')
        self.assertFalse(seconds)

    def test_exact_converted_instant_is_closed(self):
        now = datetime(2026, 12, 1, 8, 59, 59, tzinfo=ZoneInfo('Asia/Seoul'))
        with self.assertRaisesRegex(QueueValidationError, 'APPLICATION_CLOSED'):
            self.check(now=now)


if __name__ == '__main__':
    unittest.main()
