import unittest
from threads_v4.candidate_report import summarize
class CandidateReportTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(summarize({"candidates": []})["status"], "NO_CANDIDATE")
    def test_never_approves(self):
        result=summarize({"candidates":[{"notice_id":"a123","org":"기관","title":"채용"}]})
        self.assertEqual(result["approved_count"],0)
        self.assertFalse(result["candidates"][0]["official_verified"])
    def test_deduplicates(self):
        result=summarize({"candidates":[{"notice_id":"a1"},{"notice_id":"a1"}]})
        self.assertEqual(result["candidate_count"],1)
if __name__=="__main__":unittest.main()
