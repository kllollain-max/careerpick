import unittest
from unittest.mock import patch
from threads_v4.official_fetch import check_url
class Response:
    headers={"Content-Type":"text/html"}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def getcode(self):return 200
    def read(self,n):return "<html><body>채용 공고 정정 안내</body></html>".encode()
class CorrectionIntegrationTests(unittest.TestCase):
    def test_long_page_trailing_cancellation_detected(self):
        from threads_v4.official_text import extract
        from threads_v4.correction_scan import scan
        body=("<p>일반 채용 안내</p>"*5000)+"<p>본 채용 공고를 취소합니다</p>"
        extracted=extract(("<html><body>"+body+"</body></html>").encode())
        self.assertGreater(len(extracted["plain_text"]),30000)
        self.assertEqual(scan(extracted["plain_text"])["status"],"CANCELLATION_SUSPECTED")
    @patch("threads_v4.official_fetch.socket.getaddrinfo",return_value=[(None,None,None,None,("93.184.215.14",443))])
    def test_correction_requires_review(self,_):
        r=check_url("https://example.org",opener=lambda *args,**kwargs:Response())
        self.assertEqual(r["correction_scan"]["status"],"CORRECTION_REVIEW_REQUIRED")
        self.assertNotIn("plain_text",r["text_evidence"])
        self.assertEqual(r["status"],"FETCHED_NOT_VERIFIED")
if __name__=="__main__":unittest.main()
