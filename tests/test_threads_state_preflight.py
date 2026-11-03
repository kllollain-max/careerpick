import base64
import io
import json
import os
import unittest
from unittest.mock import patch
from scripts.threads_state_preflight import main


class StatePreflightTests(unittest.TestCase):
    def run_probe(self, state='historical_verified'):
        calls = []
        def opener(req, timeout):
            calls.append((req.method, req.full_url))
            if '/git/trees/' in req.full_url:
                data = {'tree':[{'path':'threads-claims/historical.json'}]}
            elif '/threads-claims/' in req.full_url:
                data = {'content':base64.b64encode(json.dumps({'state':state}).encode()).decode()}
            elif req.method == 'PUT':
                data = {'content':{'sha':'confirmed'}}
            else:
                data = {'content':base64.b64encode(json.dumps({'run_id':'99','kind':'migration_write_probe','publishes':0}).encode()).decode()}
            return io.BytesIO(json.dumps(data).encode())
        env={'GITHUB_REPOSITORY':'a/b','GITHUB_RUN_ID':'99','GH_TOKEN':'mock','PUBLISH_ENABLED':'false','MIGRATION_READY':'false'}
        with patch.dict(os.environ,env), patch('urllib.request.urlopen',side_effect=opener):
            if state == 'sending':
                with self.assertRaises(SystemExit): main()
            else:
                main()
        return calls

    def test_probe_writes_outside_actual_slot_claims(self):
        calls=self.run_probe()
        writes=[url for method,url in calls if method=='PUT']
        self.assertEqual(len(writes),1)
        self.assertIn('/threads-state-probes/99.json',writes[0])

    def test_unresolved_remote_claim_prevents_any_write(self):
        self.assertFalse(any(method=='PUT' for method,_ in self.run_probe('sending')))

    def test_enabled_gate_blocks_before_network(self):
        with patch.dict(os.environ,{'PUBLISH_ENABLED':'true'}),patch('urllib.request.urlopen') as request:
            with self.assertRaises(SystemExit): main()
            request.assert_not_called()


if __name__ == '__main__': unittest.main()
