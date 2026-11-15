import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from threads_v4.official_triage import triage, triage_report
NOW=datetime(2026,11,15,13,tzinfo=ZoneInfo("Asia/Seoul"))
def row():
    return {"notice_id":"a123","official_url":"https://example.org/notice",
            "application_period":{"end":"2026-11-20T18:00:00+09:00"}}
class OfficialTriageTests(unittest.TestCase):
    def test_valid_url_still_hold(self):
        x=triage(row(),NOW);self.assertEqual(x["decision"],"HOLD")
        self.assertFalse(x["official_verified"])
    def test_closed_rejected(self):
        x=row();x["application_period"]["end"]="2026-11-14T18:00:00+09:00"
        self.assertEqual(triage(x,NOW)["decision"],"REJECT")
    def test_no_url(self):
        x=row();x["official_url"]=None
        self.assertEqual(triage(x,NOW)["reason"],"OFFICIAL_URL_MISSING")
    def test_http_not_accepted(self):
        x=row();x["official_url"]="http://example.org"
        self.assertEqual(triage(x,NOW)["reason"],"OFFICIAL_URL_INVALID")
    def test_never_auto_pass(self):
        x=triage_report({"candidates":[row()]},NOW)
        self.assertEqual(x["pass_count"],0)
if __name__=="__main__":unittest.main()
