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
    @patch("threads_v4.official_fetch.socket.getaddrinfo",return_value=[(None,None,None,None,("93.184.215.14",443))])
    def test_correction_requires_review(self,_):
        r=check_url("https://example.org",opener=lambda *args,**kwargs:Response())
        self.assertEqual(r["correction_scan"]["status"],"CORRECTION_REVIEW_REQUIRED")
        self.assertNotIn("plain_text",r["text_evidence"])
        self.assertEqual(r["status"],"FETCHED_NOT_VERIFIED")
if __name__=="__main__":unittest.main()
