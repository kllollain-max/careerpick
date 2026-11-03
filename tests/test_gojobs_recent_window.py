import unittest
import xml.etree.ElementTree as ET
import gojobs
from scripts.verify_gojobs_recent_window import collect_window, body_application_period


def body(page, total, ids, registered='2026-11-03'):
    rows=''.join(f'<item><idx>{i}</idx><title>최종합격자 발표</title><insttname>기관</insttname><type01>e01</type01><type02>g02</type02><regdate>{registered}</regdate><enddate>20261120</enddate></item>' for i in ids)
    return ET.fromstring(f'<body><totalCount>{total}</totalCount><pageNo>{page}</pageNo><numOfRows>100</numOfRows><items>{rows}</items></body>')


class Fake(gojobs.Client):
    def __init__(self, responses):
        super().__init__('fixture-key-never-logged')
        self.responses=iter(responses)
    def _request(self, operation, params):
        self.request_counts[operation]+=1
        assert params['Begin_de']=='2026-10-20'
        assert params['End_de']=='2026-11-03'
        return next(self.responses)


class WindowTests(unittest.TestCase):
    def test_body_application_period_not_exam_dates(self):
        self.assertEqual(body_application_period('접수기간 : 2026. 11. 3.(화) ~ 11. 16.(월), 09:00 ~ 18:00'),('2026-11-03','2026-11-16'))
        self.assertEqual(body_application_period('원서접수: 2026년11월11일 ~ 2026년11월13일'),('2026-11-11','2026-11-13'))
        self.assertIsNone(body_application_period('면접시험 : 2026. 11. 3. ~ 11.16.'))
    def test_all_pages_and_results_excluded(self):
        result=collect_window(Fake([body(1,101,range(1,101)),body(2,101,[101]),body(1,0,[])]),'2026-10-20','2026-11-03')
        self.assertEqual(len(result['records']),101)
        self.assertEqual(result['total_by_filter']['e01']['pages'],2)
        self.assertEqual(result['detail_samples'],[])
        self.assertEqual(result['eligible_for_publication'],0)
    def test_missing_page_rows_rejected(self):
        with self.assertRaisesRegex(gojobs.APIError,'partial_page'):
            collect_window(Fake([body(1,101,[1])]),'2026-10-20','2026-11-03')
    def test_ignored_date_filter_rejected(self):
        with self.assertRaisesRegex(gojobs.APIError,'date_filter_not_honored'):
            collect_window(Fake([body(1,1,[1],registered='2008-11-03')]),'2026-10-20','2026-11-03')
    def test_total_changes_rejected(self):
        with self.assertRaisesRegex(gojobs.APIError,'pagination_changed'):
            collect_window(Fake([body(1,101,range(1,101)),body(2,102,[101,102])]),'2026-10-20','2026-11-03')
    def test_duplicate_between_pages_rejected(self):
        with self.assertRaisesRegex(gojobs.APIError,'duplicate_identifier'):
            collect_window(Fake([body(1,101,range(1,101)),body(2,101,[100])]),'2026-10-20','2026-11-03')


if __name__=='__main__':
    unittest.main()
