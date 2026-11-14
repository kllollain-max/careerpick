import datetime,unittest
from zoneinfo import ZoneInfo
from select_jobs import choose
NOW=datetime.datetime(2026,11,14,12,0,tzinfo=ZoneInfo("Asia/Seoul"))
def job(id,count,deadline="2026-11-20 18:00",kind="정규직",verified=True):
 return {"id":id,"headcount":count,"application_deadline":deadline,"employment_type":kind,"official_url":"https://job.alio.go.kr/notice","official_verified":verified,"deadline_evidence":{"kind":"official_application_deadline","quote":"접수마감 "+deadline,"application_deadline":deadline,"reviewed":True}}
class SelectJobsTests(unittest.TestCase):
 def test_only_verified_active_regular(self):
  selected,held=choose([job("good",10),job("past",99,"2026-11-12 18:00"),job("dateonly",88,"2026-11-25"),job("mixed",90,kind="정규직, 계약직"),job("unverified",80,verified=False)],NOW)
  self.assertEqual([x["id"] for x in selected],["good"]);self.assertEqual(len(held),4)
 def test_count_sort_and_dedup(self):
  selected,_=choose([job("a",2),job("b",10),job("b",10),job("c",5)],NOW)
  self.assertEqual([x["id"] for x in selected],["b","c","a"])
 def test_mismatched_deadline_evidence_rejected(self):
  row=job("mismatch",100);row["deadline_evidence"]["application_deadline"]="2026-11-21 18:00"
  selected,_=choose([row],NOW);self.assertFalse(selected)
 def test_quote_disagrees_with_deadline_rejected(self):
  row=job("quote_mismatch",100);row["deadline_evidence"]["quote"]="접수마감 2026-11-21 18:00"
  selected,_=choose([row],NOW);self.assertFalse(selected)
 def test_no_deadline_evidence_rejected(self):
  row=job("unsupported",100);row.pop("deadline_evidence")
  selected,_=choose([row],NOW);self.assertFalse(selected)
 def test_invalid_count_rejected(self):
  selected,_=choose([job("bad",True),job("zero",0)],NOW);self.assertFalse(selected)
 def test_expired_at_exact_second(self):
  selected,_=choose([job("closed",10,"2026-11-14 12:00")],NOW);self.assertFalse(selected)
if __name__=="__main__":unittest.main()
