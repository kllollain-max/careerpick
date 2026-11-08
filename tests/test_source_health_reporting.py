"""Offline regression test for the embedded source-health summary; no network or API calls."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/operations.yml"
MARKER = "      - name: Record unchanged or deployment result"

def embedded_code():
    section = WORKFLOW.read_text().split(MARKER, 1)[1]
    body = section.split("          python - <<'PY'", 1)[1].split("          PY", 1)[0]
    return compile(textwrap.dedent(body), "operations-reporting-embedded.py", "exec")

class SourceHealthReportTests(unittest.TestCase):
    def test_annotations(self):
        code = embedded_code()
        cases = (
            ("all_good", "unchanged", 0, False, ""),
            ("gojobs_failed", "failed_preserved", 0, True, "GOJOBS"),
            ("official_page_failed", "unchanged", 1, True, "GOJOBS_OFFICIAL_PAGE"),
        )
        for label, gojobs_status, page_failures, expected_warning, expected_source in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "operations-output").mkdir()
                (root / "exam-operation-output").mkdir()
                (root / "gojobs-operation-output").mkdir()
                (root / "cleaneye-operation-output").mkdir()
                (root / "operations-output/report.json").write_text(json.dumps({"status": "unchanged"}))
                (root / "exam-operation-output/report.json").write_text(json.dumps({"status": "unchanged"}))
                (root / "gojobs-operation-output/report.json").write_text(json.dumps({"status": gojobs_status, "official_page_failed": page_failures}))
                (root / "cleaneye-operation-output/report.json").write_text(json.dumps({"status": "unchanged"}))
                summary = root / "summary.md"
                env = {
                    "GITHUB_EVENT_NAME": "schedule",
                    "JOB_STATUS": "success",
                    "CHANGED": "false",
                    "DEPLOYMENT_OUTCOME": "skipped",
                    "STORAGE_OUTCOME": "skipped",
                    "PUBLIC_OUTCOME": "skipped",
                    "GITHUB_SERVER_URL": "https://github.com",
                    "GITHUB_REPOSITORY": "test/careerpick",
                    "GITHUB_RUN_ID": "1",
                    "GITHUB_STEP_SUMMARY": str(summary),
                }
                previous = Path.cwd()
                output = io.StringIO()
                try:
                    os.chdir(root)
                    with patch.dict(os.environ, env), contextlib.redirect_stdout(output):
                        exec(code, {"__name__": "__main__"})
                finally:
                    os.chdir(previous)
                warning = "::warning title=CareerPick source health::"
                self.assertEqual(warning in output.getvalue(), expected_warning)
                self.assertEqual(expected_source in output.getvalue() if expected_source else True, True)
                result = json.loads((root / "operations-output/report.json").read_text())
                self.assertEqual(result["overall"], "partial_or_failed" if expected_warning else "success")
                self.assertEqual("Source health warning" in summary.read_text(), expected_warning)

if __name__ == "__main__":
    unittest.main()
