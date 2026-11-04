import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_approved_head.py'

class DeploymentHeadTests(unittest.TestCase):
    def test_advancing_main_between_build_and_publish_rejects_old_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); remote = root / 'origin.git'; checkout = root / 'checkout'
            def git(*args, cwd=None):
                return subprocess.check_output(['git', *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
            git('init', '--bare', str(remote)); git('clone', str(remote), str(checkout))
            git('config', 'user.name', 'Test', cwd=checkout); git('config', 'user.email', 'test@example.invalid', cwd=checkout)
            git('checkout', '-b', 'main', cwd=checkout)
            (checkout / 'editorials.json').write_text('old link')
            git('add', '.', cwd=checkout); git('commit', '-m', 'baseline', cwd=checkout)
            old = git('rev-parse', 'HEAD', cwd=checkout); git('push', 'origin', 'main', cwd=checkout)
            def guard(sha):
                return subprocess.run([sys.executable, str(SCRIPT), '--approved-sha', sha], cwd=checkout, capture_output=True, text=True)
            self.assertEqual(guard(old).returncode, 0)
            (checkout / 'editorials.json').write_text('new published link')
            git('add', '.', cwd=checkout); git('commit', '-m', 'new blog link', cwd=checkout)
            new = git('rev-parse', 'HEAD', cwd=checkout); git('push', 'origin', 'main', cwd=checkout)
            git('checkout', '--detach', old, cwd=checkout)
            rejected = guard(old)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('main_advanced_rebuild_latest_source', rejected.stderr)
            git('checkout', '--detach', new, cwd=checkout)
            self.assertEqual(guard(new).returncode, 0)
            self.assertNotEqual(guard(old).returncode, 0)

if __name__ == '__main__': unittest.main()
