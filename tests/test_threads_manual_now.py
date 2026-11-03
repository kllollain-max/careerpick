import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from scripts.threads_auto import current_publication_slot


class ManualNowTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,3,17,30,35,tzinfo=ZoneInfo('Asia/Seoul'))
        self.env={'THREADS_MANUAL_PUBLISH':'true','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_RUN_ATTEMPT':'1','THREADS_MANUAL_SLOT':'2026-11-03T17:30:00+09:00'}

    def test_current_minute_is_separate_from_regular_slots(self):
        with patch.dict(os.environ,self.env):
            slot=current_publication_slot(self.now)
        self.assertEqual(slot.isoformat(),'2026-11-03T17:30:00+09:00')

    def test_expired_future_naive_non_kst_and_rerun_rejected(self):
        for override in [{'THREADS_MANUAL_SLOT':'2026-11-03T17:00:00+09:00'},{'THREADS_MANUAL_SLOT':'2026-11-03T20:00:00+09:00'},{'THREADS_MANUAL_SLOT':'2026-11-03T17:30:00'},{'THREADS_MANUAL_SLOT':'2026-11-03T08:30:00+00:00'},{'GITHUB_RUN_ATTEMPT':'2'},{'GITHUB_EVENT_NAME':'schedule'}]:
            with self.subTest(override=override),patch.dict(os.environ,{**self.env,**override}):
                with self.assertRaises((RuntimeError,ValueError)):current_publication_slot(self.now)

    def test_schedule_path_unchanged(self):
        with patch.dict(os.environ,{'THREADS_MANUAL_PUBLISH':'false','THREADS_SCHEDULE_CRON':'0 7 * * *'}):
            self.assertEqual(current_publication_slot(self.now).isoformat(),'2026-11-03T16:00:00+09:00')


class ActualVerificationTests(unittest.TestCase):
    def test_get_only_and_reply_connections(self):
        from scripts.threads_auto import verify_published_record
        record={'threads_post_id':'1','text':'main','reply_post_id':'2','reply_text':'detail','engagement_post_id':'3','engagement_text':'question'}
        replies=[{'id':'1','text':'main'},{'id':'2','text':'detail','is_reply':True,'root_post':{'id':'1'},'replied_to':{'id':'1'}},{'id':'3','text':'question','is_reply':True,'root_post':{'id':'1'},'replied_to':{'id':'1'}}]
        with patch('scripts.threads_auto.api',side_effect=replies) as api:
            self.assertEqual(len(verify_published_record(record,'mock')),3)
            self.assertTrue(all(c.args[0]=='GET' for c in api.call_args_list))
        replies[-1]['replied_to']={'id':'99'}
        with patch('scripts.threads_auto.api',side_effect=replies):
            with self.assertRaises(RuntimeError):verify_published_record(record,'mock')


if __name__=='__main__':unittest.main()
