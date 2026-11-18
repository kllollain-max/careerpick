import io
import unittest
from threads_v4.official_fetch import check_url
class Response:
    headers={"Content-Type":"text/html"}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def getcode(self):return 200
    def read(self,n):return b"official page"
class OfficialFetchTests(unittest.TestCase):
    def test_https_only(self):
        self.assertEqual(check_url("http://example.org")["reason"],"URL_INVALID")
    def test_success_does_not_approve(self):
        r=check_url("https://example.org",opener=lambda *args,**kwargs:Response())
        self.assertEqual(r["status"],"FETCHED_NOT_VERIFIED")
        self.assertEqual(len(r["sha256"]),64)
if __name__=="__main__":unittest.main()
