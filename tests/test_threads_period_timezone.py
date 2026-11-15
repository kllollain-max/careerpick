"""Official close timestamps must preserve the instant, precision and KST date."""
import unittest
from datetime import date, datetime

from scripts.threads_writer_queue import KST, QueueValidationError, _period_matches_excerpt


class OfficialPeriodTimezoneTests(unittest.TestCase):
    def check(self, stamp, end="2026-12-01T08:59:59+09:00"):
        evidence = '접수시작 2026. 10. 6. / "validThrough": "' + stamp + '"'
        return _period_matches_excerpt(
            {"evidence": evidence, "start_date_only": True, "date_only": False},
            date(2026, 10, 6), datetime.fromisoformat(end).astimezone(KST), {},
        )

    def test_utc_close_rolls_to_next_kst_day(self):
        self.assertTrue(self.check("2026-11-30T23:59:59+00:00"))

    def test_z_close_is_equivalent(self):
        self.assertTrue(self.check("2026-11-30T23:59:59Z"))

    def test_minute_precision_is_not_upgraded(self):
        self.assertFalse(self.check("2026-11-30T23:59+00:00", "2026-12-01T08:59:00+09:00"))

    def test_wrong_date_or_clock_rejected(self):
        for end in ["2026-11-30T23:59:59+09:00", "2026-12-01T09:00:00+09:00"]:
            with self.subTest(end=end), self.assertRaisesRegex(QueueValidationError, "TIMESTAMP_EVIDENCE_CONFLICT"):
                self.check("2026-11-30T23:59:59+00:00", end)

    def test_non_utc_offset_is_converted(self):
        self.assertTrue(self.check("2026-11-30T18:59:59-05:00"))

    def test_conflicting_structured_clocks_rejected(self):
        with self.assertRaisesRegex(QueueValidationError, "TIMESTAMP_EVIDENCE_CONFLICT"):
            self.check('2026-11-30T23:59:59Z" / "validThrough": "2026-12-01T00:00:00Z')

    def test_naive_clock_or_date_only_cannot_invent_midnight(self):
        for stamp in ["2026-11-30T23:59:59", "2026-11-30"]:
            with self.subTest(stamp=stamp), self.assertRaises(QueueValidationError):
                self.check(stamp)

    def test_unrelated_timestamp_cannot_supply_deadline(self):
        with self.assertRaises(QueueValidationError):
            _period_matches_excerpt(
                {"evidence": '시작 2026.10.6. / "dateModified": "2026-11-30T23:59:59Z"',
                 "start_date_only": True, "date_only": False}, date(2026, 10, 6),
                datetime(2026, 12, 1, 8, 59, 59, tzinfo=KST), {},
            )


if __name__ == "__main__":
    unittest.main()
