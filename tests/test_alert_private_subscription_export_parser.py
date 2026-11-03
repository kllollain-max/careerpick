import unittest

from scripts.private_subscription_export_parser import parse_subscription_ids, MAX_BYTES

SID = "717d8568-c258-4676-8761-81aa526a1a8f"


class PrivateSubscriptionExportParserTests(unittest.TestCase):
    def test_deduplicate_and_ignore_invalid(self):
        csv_data = ("subscription_id,other\n" + SID + ",x\ninvalid,y\n" + SID + ",z\n").encode()
        self.assertEqual(parse_subscription_ids(csv_data), [SID])

    def test_accept_id_header_and_bom(self):
        self.assertEqual(parse_subscription_ids(("\ufeffid\n" + SID + "\n").encode()), [SID])

    def test_reject_missing_header(self):
        with self.assertRaises(ValueError):
            parse_subscription_ids(b"email\ntest@example.com\n")

    def test_reject_oversize(self):
        with self.assertRaises(ValueError):
            parse_subscription_ids(b"x" * (MAX_BYTES + 1))

    def test_reject_over_row_cap(self):
        with self.assertRaises(ValueError):
            parse_subscription_ids(("id\n" + SID + "\n" + SID + "\n").encode(), max_rows=1)

    def test_reject_malformed_row(self):
        with self.assertRaises(ValueError):
            parse_subscription_ids(("id\n" + SID + ",extra\n").encode())


if __name__ == "__main__":
    unittest.main()
