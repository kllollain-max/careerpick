import hashlib
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from scripts.threads_live_inventory import inventory


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 16, 6, tzinfo=timezone.utc)
        self.account = {'id': '123', 'username': 'hid_119'}
        self.post = {'id': '456', 'text': 'verified public text', 'is_reply': False,
                     'timestamp': '2026-11-16T03:00:00Z',
                     'permalink': 'https://www.threads.com/@hid_119/post/example'}

    def test_remote_receipts_are_reads_and_never_authorize_resending(self):
        api = Mock(side_effect=[self.account, {'data': [self.post]}])
        result = inventory(api, 'secret-test-token', '123', self.now)
        self.assertTrue(result['pagination_complete'])
        self.assertFalse(result['safe_to_republish'])
        self.assertFalse(result['meta_posted'])
        self.assertEqual(result['posts'][0]['post_id'], '456')
        self.assertEqual(result['posts'][0]['text_sha256'], hashlib.sha256(self.post['text'].encode()).hexdigest())
        self.assertNotIn('secret-test-token', str(result))
        self.assertTrue(all(call.args[0] == 'GET' for call in api.call_args_list))

    def test_wrong_account_stops_before_reading_posts(self):
        api = Mock(return_value={**self.account, 'username': 'hid_1004'})
        with self.assertRaisesRegex(ValueError, 'THREADS_ACCOUNT_MISMATCH'):
            inventory(api, '', '123', self.now)
        self.assertEqual(api.call_count, 1)

    def test_repeated_cursor_never_loops_or_reports_complete(self):
        page = {'data': [self.post], 'paging': {'next': 'untrusted ignored url', 'cursors': {'after': 'cursor'}}}
        api = Mock(side_effect=[self.account, page, page])
        result = inventory(api, '', '123', self.now)
        self.assertEqual(result['pages_read'], 2)
        self.assertEqual(len(result['posts']), 1)
        self.assertFalse(result['pagination_complete'])
        self.assertEqual(api.call_args.args[1], '/me/threads')

    def test_page_limit_and_malformed_api_response_fail_closed(self):
        api = Mock(side_effect=[self.account, {'data': None}])
        with self.assertRaisesRegex(ValueError, 'INVENTORY_RESPONSE_INVALID'):
            inventory(api, '', '123', self.now)
        with self.assertRaisesRegex(ValueError, 'INVENTORY_BOUNDS_INVALID'):
            inventory(api, '', '123', self.now, max_pages=5)


if __name__ == '__main__':
    unittest.main()
