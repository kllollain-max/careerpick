"""Official clock precision can refine, but never replace, API calendar dates."""
from copy import deepcopy
import unittest
from scripts.threads_writer_queue import _cleaneye_application_period, QueueValidationError


class OfficialPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.detail = {'접수개시일 원문': '2026-11-03', '접수마감일 원문': '2026-11-11'}
        self.period = {'start': '2026-11-03T09:00:00+09:00', 'start_date_only': False,
                       'end': '2026-11-11T10:00:00+09:00', 'date_only': False,
                       'official_precision_verified': True}

    def test_explicitly_reviewed_same_date_clock_is_allowed(self):
        _cleaneye_application_period(self.period, self.detail)

    def test_clock_without_explicit_official_review_is_rejected(self):
        self.period.pop('official_precision_verified')
        with self.assertRaisesRegex(QueueValidationError, 'CLEANEYE_APPLICATION_PRECISION_CONFLICT'):
            _cleaneye_application_period(self.period, self.detail)

    def test_calendar_date_cannot_change(self):
        self.period['end'] = '2026-11-12T10:00:00+09:00'
        with self.assertRaisesRegex(QueueValidationError, 'CLEANEYE_APPLICATION_PERIOD_CONFLICT'):
            _cleaneye_application_period(self.period, self.detail)

    def test_official_api_clock_cannot_be_downgraded(self):
        self.detail['접수마감일 원문'] = '2026-11-11 10:00:00'
        self.period.update(end='2026-11-11', date_only=True)
        with self.assertRaisesRegex(QueueValidationError, 'CLEANEYE_APPLICATION_PRECISION_CONFLICT'):
            _cleaneye_application_period(self.period, self.detail)
