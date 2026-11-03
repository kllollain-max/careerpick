import unittest
from datetime import date
from scripts.threads_auto import candidates, compose, compose_reply, validate_candidate

class ThreadsCandidateTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 10, 24)
        self.job = {'id': 'a123', 'org': '테스트기관', 'title': '정규직 채용', 'url': 'https://job.alio.go.kr/recruit.do?id=a123', 'due': '2026-11-05', 'emp': ['정규직'], 'n': '16'}

    def test_eligible(self):
        self.assertTrue(validate_candidate(self.job, self.today))
        self.assertEqual(len(candidates([self.job], {'posted_ids': [], 'records': []}, self.today)), 1)

    def test_deadline(self):
        for due in ('2026-10-23', '2026-10-25', '2026-11-30', 'invalid'):
            with self.subTest(due=due):
                self.assertFalse(validate_candidate({**self.job, 'due': due}, self.today))

    def test_untrusted_url(self):
        for url in ('http://job.alio.go.kr/post', 'https://example.org/post', 'https://job.alio.go.kr.evil.test/post'):
            with self.subTest(url=url):
                self.assertFalse(validate_candidate({**self.job, 'url': url}, self.today))

    def test_deduplication(self):
        self.assertEqual(len(candidates([self.job, self.job], {'posted_ids': [], 'records': []}, self.today)), 1)
        self.assertFalse(candidates([self.job], {'posted_ids': ['a123'], 'records': []}, self.today))

    def test_primary_and_reply(self):
        selected = candidates([self.job], {'posted_ids': [], 'records': []}, self.today)[0]
        self.assertIn('🏢 테스트기관', compose(selected))
        self.assertIn('정규직 16명 모집', compose(selected))
        self.assertIn('11월 5일 마감', compose(selected))
        self.assertIn('답글 확인', compose(selected))
        self.assertLessEqual(len(compose(selected)), 500)
        reply = compose_reply(selected)
        self.assertIn('16명', reply)
        self.assertIn('프로필 링크의 커리어픽', reply)
        self.assertNotIn('지원자격:', reply)
        self.assertLessEqual(len(reply), 500)

if __name__ == '__main__':
    unittest.main()
