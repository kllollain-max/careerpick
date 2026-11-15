"""Exercise real retry control flow with offline command stubs, never apt/pip."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DependencySetupTests(unittest.TestCase):
    def run_setup(self, fail_always=False, fail_pip=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stubs = {
                'timeout': 'shift; exec "$@"',
                'sudo': 'exec "$@"',
                'sleep': 'exit 0',
                'apt-get': '''echo apt >> "$TRACE"
n=0; [[ ! -f "$COUNTER" ]] || n=$(cat "$COUNTER")
n=$((n+1)); echo "$n" > "$COUNTER"
if [[ "$FAIL_ALWAYS" == 1 || "$n" -lt 3 ]]; then exit 100; fi''',
                'python': 'echo pip >> "$TRACE"; if [[ "$FAIL_PIP" == 1 ]]; then exit 9; fi',
            }
            for name, source in stubs.items():
                p = root / name
                p.write_text('#!/usr/bin/env bash\n' + source + '\n')
                p.chmod(0o755)
            trace = root / 'trace'
            env = {**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'],
                   'TRACE': str(trace), 'COUNTER': str(root / 'counter'),
                   'FAIL_ALWAYS': str(int(fail_always)), 'FAIL_PIP': str(int(fail_pip))}
            result = subprocess.run(['bash', str(ROOT / 'scripts/threads_install_card_deps.sh')],
                                    env=env, capture_output=True, text=True, timeout=10)
            return result, trace.read_text().splitlines()

    def test_transient_download_recovers_then_runs_all_dependencies(self):
        result, calls = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ['apt'] * 4 + ['pip'])
        self.assertIn('retry 2 of 2', result.stderr)

    def test_persistent_failure_stops_after_three_without_skipping_gate(self):
        result, calls = self.run_setup(fail_always=True)
        self.assertEqual(result.returncode, 100)
        self.assertEqual(calls, ['apt'] * 3)
        self.assertIn('failed after 3 attempts', result.stderr)

    def test_pip_failure_stays_failed_and_is_bounded(self):
        result, calls = self.run_setup(fail_pip=True)
        self.assertEqual(result.returncode, 9)
        self.assertEqual(calls.count('pip'), 3)
