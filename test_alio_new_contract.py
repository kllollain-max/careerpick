import io
import json
import unittest
from unittest.mock import patch
import alio

class ContractTest(unittest.TestCase):
    def response(self, obj):
        return io.BytesIO(json.dumps(obj).encode())
    def test_post_query_and_detail(self):
        def reply(req, timeout):
            self.assertEqual(req.method, "POST")
            self.assertEqual(req.data, b"")
            self.assertIn("serviceKey=test%2Bkey", req.full_url)
            self.assertTrue(req.full_url.startswith("https://opendata.alio.go.kr/new/v1/recruit/"))
            if "/detail.do?" in req.full_url:
                self.assertIn("sn=123", req.full_url)
                return self.response({"resultCode":200,"result":{"recrutPblntSn":123}})
            self.assertIn("pageNo=1", req.full_url)
            return self.response({"resultCode":200,"totalCount":1,"result":[{"recrutPblntSn":123}]})
        with patch("alio.urllib.request.urlopen", side_effect=reply):
            self.assertEqual(alio.call("test+key",1)["totalCount"],1)
            self.assertEqual(alio.call_detail("test+key",123)["recrutPblntSn"],123)
    def test_reject_error_shape_and_wrong_identity(self):
        for payload in [
            {"resultCode":8,"result":[],"totalCount":0},
            {"resultCode":0,"result":{},"totalCount":1},
            {"resultCode":0,"result":[]},
            {"resultCode":0,"result":[],"totalCount":-1},
        ]:
            with self.subTest(payload=payload), patch("alio.urllib.request.urlopen",return_value=self.response(payload)):
                with self.assertRaises(RuntimeError):
                    alio.call("secret",1)
        with patch("alio.urllib.request.urlopen",return_value=self.response({"resultCode":0,"result":{"recrutPblntSn":456}})):
            with self.assertRaises(RuntimeError):
                alio.call_detail("secret",123)
    def test_transport_error_redacts_secret(self):
        with patch("alio.urllib.request.urlopen",side_effect=Exception("https://host/?serviceKey=SECRET")):
            with self.assertRaises(RuntimeError) as caught:
                alio.call("SECRET",1)
            self.assertNotIn("SECRET",str(caught.exception))
            self.assertNotIn("https",str(caught.exception))
if __name__ == "__main__":
    unittest.main()
