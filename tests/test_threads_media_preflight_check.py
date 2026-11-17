import unittest
from scripts.threads_media_preflight_check import check_report


class CurrentForecastChecks(unittest.TestCase):
    def setUp(self):
        self.report = {'future_slots': ['2026-11-18T12:00:00+09:00'],
            'approved_future_slots': ['2026-11-18T12:00:00+09:00'],
            'invalid_ready_entries': [], 'next_slot_missing': False}

    def test_current_day_passes_without_yesterdays_slot(self):
        self.assertEqual(check_report(self.report), self.report['future_slots'][0])

    def test_any_invalid_notice_blocks_ci(self):
        self.report['invalid_ready_entries'] = [{'notice_id': 'different-notice', 'reason': 'CARD_VISUAL_REVIEW_REQUIRED'}]
        with self.assertRaisesRegex(ValueError, 'INVALID_REVIEWED'):check_report(self.report)

    def test_missing_next_slot_is_not_certified(self):
        self.report['approved_future_slots'] = []
        with self.assertRaisesRegex(ValueError, 'NEXT_REVIEWED'):check_report(self.report)

    def test_old_approval_does_not_certify_current_supply(self):
        self.report['approved_future_slots'].append('2026-11-17T16:00:00+09:00')
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_CURRENT'):check_report(self.report)

    def test_missing_report_fields_fail_closed(self):
        del self.report['invalid_ready_entries']
        with self.assertRaisesRegex(ValueError, 'MEDIA_REPORT_SCHEMA'):check_report(self.report)
