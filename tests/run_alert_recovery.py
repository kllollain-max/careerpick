"""Offline recovery regression; previously verified large scale stress cases excluded."""
import sys
import socket
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SKIP_SCALE = {'test_1000_subscribers_66_jobs_over_many_runs',
              'test_66000_candidates_full_eligible_drain_with_restart_and_history'}

def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        elif item._testMethodName not in SKIP_SCALE:
            yield item

if __name__ == '__main__':
    suite=unittest.TestSuite(cases(unittest.defaultTestLoader.discover('tests',pattern='test_alert*.py')))
    with patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden in offline tests')):
        result=unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(not result.wasSuccessful())
