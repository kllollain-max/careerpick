"""The paused targeted-push workflow may run only from a manual dispatch.

This test deliberately inspects the workflow rather than relying on a live secret.
"""
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/targeted-push.yml"

class PushHoldWorkflowTests(unittest.TestCase):
    def test_automatic_triggers_removed_and_manual_gate_present(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:", text)
        self.assertNotIn("  workflow_run:", text)
        self.assertNotIn("  schedule:", text)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", text)
        self.assertIn("CP_PUSH_MODE:", text)

    def test_existing_offline_sender_safety_test_still_required(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python tests/run_alert_recovery.py", text)
        self.assertNotIn("mode: run", text)

if __name__ == "__main__":
    unittest.main()
