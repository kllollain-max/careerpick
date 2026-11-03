"""No-network scheduler planner tests; no OneSignal sends."""
import unittest
from datetime import datetime, timedelta
from scripts.detect_new_job_alerts import KST
from scripts.alert_delivery_ledger import delivery_key
from scripts.rollout_batch_planner import eligible_pairs


class BatchPlannerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(KST)
        self.jobs = [
            {"id": "a" + str(i), "title": "Job " + str(i),
             "due": (self.now + timedelta(days=4)).strftime("%Y-%m-%d"),
             "region": "서울", "emp": "정규직", "cat": "IT"}
            for i in range(66)
        ]
        self.tags = {"cp_optin": "yes", "cp_profile":
                     '{"v":4,"region":["서울"],"employment":[],"education":[],"category":[],"keywords":""}'}

    def subs(self, count):
        return [{"opted_in": True, "subscription_id": "synthetic-%d" % i, "tags": self.tags}
                for i in range(count)]

    def test_sizes_and_cap(self):
        for size in (2, 100, 101, 1000):
            with self.subTest(size=size):
                pairs = eligible_pairs(self.jobs, self.subs(size),
                                       {"delivered": [], "pending": []}, self.now, 3)
                self.assertEqual(len(pairs), 3)

    def test_resume_after_durable_delivery(self):
        subs = self.subs(2)
        state = {"delivered": [], "pending": []}
        first = eligible_pairs(self.jobs, subs, state, self.now, 3)
        state["delivered"] = [delivery_key(job["id"], sub["subscription_id"])
                              for job, sub in first]
        second = eligible_pairs(self.jobs, subs, state, self.now, 3)
        self.assertEqual(len(second), 3)
        self.assertFalse(set((j["id"], s["subscription_id"]) for j, s in first)
                         & set((j["id"], s["subscription_id"]) for j, s in second))

    def test_pending_is_not_retried(self):
        subs = self.subs(1)
        key = delivery_key(self.jobs[0]["id"], subs[0]["subscription_id"])
        pairs = eligible_pairs(self.jobs, subs,
                               {"delivered": [], "pending": [key]}, self.now, 3)
        self.assertEqual(len(pairs), 3)
        self.assertNotEqual(pairs[0][0]["id"], self.jobs[0]["id"])

    def test_unmatched_and_new_jobs(self):
        subs = self.subs(1)
        no_match = dict(self.jobs[0], region="부산")
        self.assertEqual(eligible_pairs([no_match], subs,
                         {"delivered": [], "pending": []}, self.now, 3), [])
        self.assertEqual(len(eligible_pairs(self.jobs + [dict(self.jobs[0], id="anew")],
                                            subs, {"delivered": [], "pending": []},
                                            self.now, 100)), 67)


if __name__ == "__main__":
    unittest.main()
