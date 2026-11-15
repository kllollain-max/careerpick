"""Regression tests for safe Threads dispatch and empty-queue recovery.

Run: python -m unittest tests.test_threads_emergency_dispatch
No network, Meta API calls, or GitHub writes.
"""
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts import threads_auto as publisher
from scripts.threads_writer_queue import QueueValidationError

KST = ZoneInfo("Asia/Seoul")


class EmergencyDispatchTests(unittest.TestCase):
    def test_manual_dispatch_current_regular_slot(self):
        now = datetime(2026, 11, 15, 12, 35, tzinfo=KST)
        with patch.dict(os.environ, {
            "THREADS_MANUAL_PUBLISH": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_RUN_ATTEMPT": "1",
            "THREADS_MANUAL_SLOT": "2026-11-15T12:00:00+09:00",
        }):
            self.assertEqual(publisher.current_publication_slot(now).hour, 12)

    def test_manual_dispatch_rejects_arbitrary_minute(self):
        now = datetime(2026, 11, 15, 12, 35, tzinfo=KST)
        with patch.dict(os.environ, {
            "THREADS_MANUAL_PUBLISH": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_RUN_ATTEMPT": "1",
            "THREADS_MANUAL_SLOT": "2026-11-15T12:35:00+09:00",
        }):
            with self.assertRaisesRegex(RuntimeError, "regular KST slot"):
                publisher.current_publication_slot(now)

    def test_manual_dispatch_rejects_expired_window(self):
        now = datetime(2026, 11, 15, 14, 1, tzinfo=KST)
        with patch.dict(os.environ, {
            "THREADS_MANUAL_PUBLISH": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_RUN_ATTEMPT": "1",
            "THREADS_MANUAL_SLOT": "2026-11-15T12:00:00+09:00",
        }):
            with self.assertRaisesRegex(RuntimeError, "within the current"):
                publisher.current_publication_slot(now)

    def test_empty_approved_queue_does_not_reserve_or_publish(self):
        history = {"posted_ids": [], "records": []}
        now = datetime(2026, 11, 15, 12, 10, tzinfo=KST)
        slot = now.replace(minute=0, second=0, microsecond=0)
        with patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "1"}, clear=False), \
             patch.object(publisher, "current_publication_slot", return_value=slot), \
             patch.object(publisher, "writer_inputs", return_value=({}, {}, {})), \
             patch.object(publisher, "load", return_value={"schema_version": 1, "entries": []}), \
             patch("scripts.threads_writer_queue.select_ready", side_effect=QueueValidationError("QUEUE_SLOT_MISSING")), \
             patch.object(publisher, "save") as save_mock:
            publisher.prepare_master(history, now, "12345")
        self.assertEqual(history["records"], [])
        save_mock.assert_not_called()

    def test_other_queue_validation_errors_are_not_suppressed(self):
        history = {"posted_ids": [], "records": []}
        now = datetime(2026, 11, 15, 12, 10, tzinfo=KST)
        slot = now.replace(minute=0, second=0, microsecond=0)
        with patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "1"}, clear=False), \
             patch.object(publisher, "current_publication_slot", return_value=slot), \
             patch.object(publisher, "writer_inputs", return_value=({}, {}, {})), \
             patch.object(publisher, "load", return_value={"schema_version": 1, "entries": []}), \
             patch("scripts.threads_writer_queue.select_ready", side_effect=QueueValidationError("SOURCE_STALE")):
            with self.assertRaisesRegex(QueueValidationError, "SOURCE_STALE"):
                publisher.prepare_master(history, now, "12345")

    def test_manual_dispatch_requires_matching_reviewed_notice(self):
        history = {"posted_ids": [], "records": []}
        now = datetime(2026, 11, 15, 12, 10, tzinfo=KST)
        slot = now.replace(minute=0, second=0, microsecond=0)
        with patch.dict(os.environ, {
            "GITHUB_RUN_ATTEMPT": "1",
            "THREADS_MANUAL_PUBLISH": "true",
            "THREADS_DISPATCH_NOTICE_ID": "a111111",
        }), patch.object(publisher, "current_publication_slot", return_value=slot), \
             patch.object(publisher, "writer_inputs", return_value=({}, {}, {})), \
             patch.object(publisher, "load", return_value={"schema_version": 1, "entries": []}), \
             patch("scripts.threads_writer_queue.select_ready", return_value={"job_id": "a222222"}), \
             patch.object(publisher, "save") as save_mock:
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                publisher.prepare_master(history, now, "12345")
        save_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
