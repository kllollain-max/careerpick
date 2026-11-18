import unittest
from threads_v4.cutover_gate import evaluate
class CutoverTests(unittest.TestCase):
    def test_no_post_blocks(self):
        r=evaluate(verified_post=False,receipt={},backup=False,old_disabled=False,
                   v4_enabled=False,queue_ready=False,image_reviewed=False)
        self.assertFalse(r["cutover_allowed"])
    def test_double_enabled_not_ready(self):
        r=evaluate(verified_post=True,receipt={"id":"1","permalink":"https://threads.net/a"},
                   backup=True,old_disabled=False,v4_enabled=True,queue_ready=True,image_reviewed=True)
        self.assertFalse(r["cutover_allowed"])
    def test_unverified_switch_unsafe(self):
        r=evaluate(verified_post=False,receipt={},backup=True,old_disabled=True,
                   v4_enabled=True,queue_ready=True,image_reviewed=True)
        self.assertEqual(r["status"],"UNSAFE_CUTOVER")
if __name__=="__main__":unittest.main()
