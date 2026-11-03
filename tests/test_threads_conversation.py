import os
import unittest
from unittest.mock import patch
from scripts.threads_editorial import conversation_main
from scripts.threads_auto import compose, MAX_DAILY


class ThreadsConversationTests(unittest.TestCase):
    def setUp(self):
        self.job = {
            "id": "test123", "org": "테스트공단", "title": "정보보안 전산직",
            "employment": "정규직", "count": 12, "location": "부산",
            "due": "2026-11-05"
        }

    def test_hook_and_facts_in_main(self):
        with patch.dict(os.environ, {"THREADS_CONVERSATION_ENABLED": "true"}):
            result = compose(self.job)
        self.assertTrue(result.startswith("정규직 채용!"))
        self.assertIn("12명 모집", result)
        self.assertIn("부산", result)
        self.assertIn("2026-11-05", result)
        self.assertIn("댓글", result)
        self.assertLessEqual(len(result), 500)

    def test_no_invented_competition_or_salary(self):
        text = conversation_main(self.job)
        self.assertNotIn("경쟁률", text)
        self.assertNotIn("연봉", text)
        self.assertNotIn("섀도우밴", text)

    def test_daily_limit(self):
        self.assertEqual(MAX_DAILY, 4)

    def test_fallback_without_flag(self):
        with patch.dict(os.environ, {"THREADS_CONVERSATION_ENABLED": "false", "THREADS_EDITORIAL_ENABLED": "true"}):
            self.assertIn("📢 공공기관 채용정보", compose(self.job))


if __name__ == "__main__":
    unittest.main()
