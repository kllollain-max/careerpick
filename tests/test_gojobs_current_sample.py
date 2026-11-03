import contextlib
import io
import json
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import gojobs
from scripts import verify_gojobs_current_sample as probe
from test_gojobs import KEY, Opener, detail_xml, list_xml, row

NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)


class CurrentSampleProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "alio.json").write_text('{"posts":[{"id":"existing"}]}')
        (self.root / "alio-detail.json").write_text('{"existing":{"title":"preserve"}}')
        self.before = {name: (self.root / name).read_bytes() for name in probe.SOURCE_NAMES}
        self.network = mock.patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("unexpected_network"))
        self.network.start()

    def tearDown(self):
        self.network.stop()
        self.tmp.cleanup()

    def factory(self, *payloads):
        client = probe.CurrentSampleClient(KEY)
        client._opener = Opener(payloads)
        return client, lambda key: client

    def run_probe(self, factory, **kwargs):
        return probe.verify(self.root, key=KEY, client_factory=factory, now=NOW, **kwargs)

    def assert_source_preserved(self, report):
        self.assertTrue(report["source_preserved"])
        self.assertEqual(self.before, {name: (self.root / name).read_bytes() for name in self.before})
        paths = list((self.root / "gojobs-current-sample-output").iterdir())
        self.assertEqual([path.name for path in paths], ["report.json"])

    def test_desc_only_replaces_list_parameter_and_reports_observed_dates(self):
        client, factory = self.factory(
            list_xml(row(1, regdate="20081201", enddate="20081231"), row(2, enddate="20261103")),
            list_xml(row(3, "e02", enddate="20270105")),
            detail_xml(1), detail_xml(3, "e02"), detail_xml(2))
        report = self.run_probe(factory)
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["requests"], {"list": 2, "detail": 3})
        self.assertEqual(report["mpm_requests"], 0)
        self.assertFalse(report["official_sort_mapping_verified"])
        self.assertFalse(report["latest_order_verified"])
        self.assertEqual(report["result"]["filters"]["Sort_order"], "DESC")
        for index, request in enumerate(client._opener.requests):
            address = urllib.parse.urlsplit(request.full_url)
            query = urllib.parse.parse_qs(address.query)
            self.assertEqual(address.scheme + "://" + address.netloc, "https://apis.data.go.kr")
            self.assertTrue(address.path.startswith("/1760000/PblJobService/"))
            self.assertEqual(query["serviceKey"], [KEY])
            if index < 2:
                self.assertEqual(set(query), {"serviceKey", "pageNo", "numOfRows", "Pblanc_ty", "Instt_se", "Sort_order"})
                self.assertEqual(query["Sort_order"], ["DESC"])
                self.assertEqual(query["Instt_se"], ["g02"])
            else:
                self.assertEqual(set(query), {"serviceKey", "idx"})
        dates = report["date_observations"]
        self.assertEqual(dates["registered_date"]["min"], "2008-12-01")
        self.assertEqual(dates["registered_date"]["max"], "2026-11-03")
        self.assertEqual(dates["registered_date"]["year_counts"], {"2008": 1, "2026": 2})
        self.assertEqual(dates["deadline"]["year_counts"], {"2008": 1, "2026": 1, "2027": 1})
        self.assertEqual(dates["deadline_on_or_after_check_date_ids"], ["2", "3"])
        self.assertFalse(dates["authoritative_open_status_verified"])
        self.assert_source_preserved(report)

    def test_partial_failure_retains_safe_progress_and_does_not_claim_empty_category(self):
        client, factory = self.factory(list_xml(row(4), row(7), row(20)), list_xml(),
                                       detail_xml(4), detail_xml(7),
                                       detail_xml(20, type01="g01", type02="RAW_CODE", title="FAILED_TITLE"))
        report = self.run_probe(factory)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["reason"], "invalid_classification_pair")
        self.assertTrue(report["authentication_verified"])
        progress = report["verification_progress"]
        self.assertEqual(progress["failed_notice"]["id"], "20")
        self.assertEqual([item["id"] for item in progress["detail_samples"]], ["4", "7"])
        self.assertFalse(progress["verification_complete"])
        self.assertEqual(report["response_diagnostic"], {"observed_filters": {"type01": "g01", "type02": "unknown"}})
        self.assertEqual(report["date_observations"]["filter_observations"]["e02"], {
            "query_verified": True, "total_count": 0, "sample_count": 0,
            "detail_verified_count": 0, "records_observed": False})
        self.assertEqual(len(client._opener.requests), 5)
        for private in ("RAW_CODE", "FAILED_TITLE", KEY):
            self.assertNotIn(private, json.dumps(report))
        with mock.patch.object(probe, "verify", return_value=report), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(probe.main(), 2)
        self.assert_source_preserved(report)

    def test_missing_dates_are_not_inferred_and_empty_lists_remain_explicit(self):
        _, factory = self.factory(list_xml(row(1, regdate="", enddate="")), list_xml(), detail_xml(1))
        report = self.run_probe(factory)
        dates = report["date_observations"]
        self.assertEqual(dates["registered_date"]["provided_count"], 0)
        self.assertIsNone(dates["deadline"]["max"])
        self.assertIsNone(dates["rows"][0]["check_date_on_or_before_deadline"])
        self.assertEqual(dates["deadline_on_or_after_check_date_ids"], [])
        _, factory = self.factory(list_xml(), list_xml())
        report = self.run_probe(factory)
        self.assertTrue(report["authentication_verified"])
        self.assertEqual(report["requests"], {"list": 2, "detail": 0})
        self.assertFalse(report["result"]["detail_verified"])
        self.assertEqual(report["date_observations"]["rows"], [])

    def test_auth_transport_and_secret_echo_fail_safely_without_retry(self):
        cases = [(list_xml(code="30"), "api_result_30"), (RuntimeError(KEY), "transport_error"),
                 (list_xml(row(1, title=KEY)), "credential_echo_rejected"),
                 (list_xml(row(1, title=urllib.parse.quote(KEY, safe=""))), "credential_echo_rejected")]
        for payload, expected in cases:
            with self.subTest(code=expected):
                client, factory = self.factory(payload)
                captured_out, captured_err = io.StringIO(), io.StringIO()
                def noisy_factory(key):
                    print(key)
                    print(key, file=probe.sys.stderr)
                    return factory(key)
                with contextlib.redirect_stdout(captured_out), contextlib.redirect_stderr(captured_err):
                    report = self.run_probe(noisy_factory)
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["reason"], expected)
                self.assertEqual(len(client._opener.requests), 1)
                self.assertFalse(report["authentication_verified"])
                text = (self.root / "gojobs-current-sample-output" / "report.json").read_text()
                for private in (KEY, urllib.parse.quote(KEY, safe="")):
                    self.assertNotIn(private, text + captured_out.getvalue() + captured_err.getvalue())
                self.assert_source_preserved(report)

    def test_only_gojobs_environment_credential_is_accessed(self):
        _, factory = self.factory(list_xml(), list_xml())
        environment = mock.Mock()
        environment.get.side_effect = lambda name, default="": {"GOJOBS_KEY": KEY, "GITHUB_SHA": ""}[name]
        with mock.patch.object(probe.os, "environ", environment):
            report = probe.verify(self.root, client_factory=factory, now=NOW)
        self.assertEqual(report["status"], "verified")
        self.assertEqual([call.args[0] for call in environment.get.call_args_list], ["GOJOBS_KEY", "GITHUB_SHA"])

    def test_source_mutation_invalidates_success_and_cli_status(self):
        client, factory = self.factory(list_xml(), list_xml())
        original_verify = client.verify
        def changed_source():
            result = original_verify()
            (self.root / "alio.json").write_text('{"posts":[]}')
            return result
        client.verify = changed_source
        report = self.run_probe(factory)
        self.assertFalse(report["source_preserved"])
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["reason"], "source_changed_or_unreadable")
        with mock.patch.object(probe, "verify", return_value=report), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(probe.main(), 2)

    def test_missing_key_blocks_client_creation(self):
        factory = mock.Mock(side_effect=AssertionError("must_not_initialize"))
        report = probe.verify(self.root, key="", client_factory=factory, now=NOW)
        factory.assert_not_called()
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "missing_secret")
        self.assert_source_preserved(report)


if __name__ == "__main__":
    unittest.main()
