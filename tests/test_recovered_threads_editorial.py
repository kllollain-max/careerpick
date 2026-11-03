import unittest
from scripts.threads_editorial import engagement, enrich_main, validated_reply


class ThreadsEditorialTests(unittest.TestCase):
    def test_all_roles(self):
        for title in ("전산직", "전기 시설", "연구원", "행정"):
            job = {"id": "abc", "org": "테스트기관", "title": title}
            main = enrich_main("📢 공공기관 채용정보\n\n💬 지원자격·접수정보는 답글 확인", job)
            self.assertLessEqual(len(main), 500)
            self.assertIn("💬 지원자격·접수정보는 답글 확인", main)
            self.assertTrue(validated_reply(engagement(job)))

    def test_deterministic(self):
        job = {"id": "same", "title": "전산"}
        self.assertEqual(engagement(job), engagement(job))

    def test_overflow_falls_back(self):
        text = "x" * 480 + "💬 지원자격·접수정보는 답글 확인"
        self.assertEqual(enrich_main(text, {"title": "전산"}), text)

    def test_no_unverified_salary_or_ai_predictions(self):
        job = {"id": "1", "title": "전산직"}
        text = enrich_main("💬 지원자격·접수정보는 답글 확인", job)
        self.assertNotIn("연봉", text)
        self.assertNotIn("유망 ↑", text)

    def test_publish_records_both_replies_without_network(self):
        from unittest.mock import patch
        from scripts import threads_auto
        history = {"posted_ids": [], "records": []}
        record = {
            "job_id": "mock-job", "status": "pending",
            "run_id": "50", "scheduled_at": "2026-10-29T12:00:00+09:00",
            "text": "sample", "reply_text": "details",
            "engagement_text": "question", "image_url": "",
        }
        history["records"].append(record)
        issued = []
        def fake_media(token, params):
            issued.append(params)
            return ["main-id", "detail-id", "engagement-id"][len(issued)-1]
        with patch.dict("os.environ", {"THREADS_ENABLED": "true", "THREADS_ACCESS_TOKEN": "mock"}), \
             patch("scripts.threads_remote_claim.GitHubClaims") as claim, \
             patch.object(threads_auto, "verify_account", return_value="123"), \
             patch.object(threads_auto, "api", return_value={"id": "main-id"}), \
             patch.object(threads_auto, "create_media", side_effect=fake_media), \
             patch.object(threads_auto, "save"), \
             patch.object(threads_auto.time, "sleep"):
            threads_auto.publish_post(record, history)
            threads_auto.publish_post(record, history)
        self.assertEqual(len(issued), 3)
        self.assertEqual(issued[1]["reply_to_id"], "main-id")
        self.assertEqual(issued[2]["reply_to_id"], "main-id")
        self.assertEqual(record["engagement_post_id"], "engagement-id")

    def test_second_reply_failure_preserves_main_and_first_reply(self):
        from unittest.mock import patch
        from scripts import threads_auto
        history = {"posted_ids": [], "records": []}
        record = {
            "job_id": "mock-failure", "status": "pending",
            "run_id": "50", "scheduled_at": "2026-10-29T12:00:00+09:00",
            "text": "sample", "reply_text": "details",
            "engagement_text": "question", "image_url": "",
        }
        history["records"].append(record)
        calls = []
        def fake_media(token, params):
            calls.append(params)
            if len(calls) == 3:
                raise RuntimeError("mock Threads API error")
            return ("main-id", "detail-id")[len(calls) - 1]
        with patch.dict("os.environ", {"THREADS_ENABLED": "true", "THREADS_ACCESS_TOKEN": "mock"}), \
             patch("scripts.threads_remote_claim.GitHubClaims") as claim, \
             patch.object(threads_auto, "verify_account", return_value="123"), \
             patch.object(threads_auto, "api", return_value={"id": "main-id"}), \
             patch.object(threads_auto, "create_media", side_effect=fake_media), \
             patch.object(threads_auto, "save"), \
             patch.object(threads_auto.time, "sleep"):
            threads_auto.publish_post(record, history)
            threads_auto.publish_post(record, history)
        self.assertEqual(len(calls), 3)
        self.assertEqual(record["threads_post_id"], "main-id")
        self.assertEqual(record["reply_post_id"], "detail-id")
        self.assertNotIn("engagement_post_id", record)
        self.assertEqual(record["engagement_status"], "needs_review")

    def test_feature_flag_defaults_off(self):
        from unittest.mock import patch
        from scripts import threads_auto
        job = {"id": "test", "org": "테스트", "title": "전산", "due": "2026-11-05", "emp": ["정규직"], "n": "3"}
        with patch.dict("os.environ", {"THREADS_EDITORIAL_ENABLED": "false"}):
            text = threads_auto.compose(job)
        self.assertNotIn("커리어픽 직무 관점", text)
        with patch.dict("os.environ", {"THREADS_EDITORIAL_ENABLED": "true"}):
            enabled = threads_auto.compose(job)
        self.assertIn("커리어픽 직무 관점", enabled)


if __name__ == "__main__":
    unittest.main()
