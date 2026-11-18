import unittest
from threads_v4.official_text import extract
class TextTests(unittest.TestCase):
    def test_extract(self):
        r=extract(b"<html><body>Institution 10 positions</body></html>",terms=["10 positions"])
        self.assertTrue(r["evidence"]["10 positions"]["found"])
        self.assertEqual(r["status"],"SNIPPETS_ONLY_NOT_VERIFIED")
    def test_script_ignored(self):
        r=extract(b"<script>10 positions</script><p>Other</p>",terms=["10 positions"])
        self.assertFalse(r["evidence"]["10 positions"]["found"])
if __name__=="__main__":unittest.main()
