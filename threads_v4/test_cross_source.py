import unittest
from threads_v4.cross_source import compare
def source(fields):
    return {"status":"FETCHED_NOT_VERIFIED","text_evidence":{"evidence":{k:{"found":v} for k,v in fields.items()}}}
class CrossSourceTests(unittest.TestCase):
    def test_incomplete(self):
        self.assertEqual(compare([])["reason"],"OFFICIAL_SOURCE_FETCH_INCOMPLETE")
    def test_cross_check_never_auto_approves(self):
        terms={"한국조세재정연구원":True,"연구위원":True,"10명":True,"정규직":True}
        result=compare([source(terms),source(terms)])
        self.assertEqual(result["decision"],"HOLD")
        self.assertFalse(result["official_approved"])
    def test_mismatch(self):
        terms={"한국조세재정연구원":True,"연구위원":True,"10명":True,"정규직":True}
        other={**terms,"10명":False}
        self.assertEqual(compare([source(terms),source(other)])["reason"],"CROSS_SOURCE_FACT_MISMATCH")
if __name__=="__main__":unittest.main()
