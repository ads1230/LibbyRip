"""Pure local validation tests: no calls to Libby or OverDrive."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from libby_handoff_server import LOAN_PATH_RE, validate_loan


class LoanHandoffTests(unittest.TestCase):
    def test_valid_loan(self):
        result = validate_loan({
            "url": "https://libbyapp.com/open/loan/97598119/9910726",
            "title": "Example Book",
            "author": "Example Author",
        })
        self.assertEqual(result["loan_reference"], ["97598119", "9910726"])
        self.assertEqual(result["title"], "Example Book")
        self.assertEqual(result["author"], "Example Author")

    def test_strips_query_and_fragment(self):
        result = validate_loan({
            "url": "https://libbyapp.com/open/loan/97598119/9910726?token=do-not-store#chapter",
            "title": " Hello  World ",
        })
        self.assertEqual(result["url"], "https://libbyapp.com/open/loan/97598119/9910726")
        self.assertEqual(result["title"], "Hello World")

    def test_rejects_other_sites(self):
        for url in (
            "https://evil.test/open/loan/1/2",
            "https://libbyapp.com.evil.test/open/loan/1/2",
            "http://libbyapp.com/open/loan/1/2",
            "https://libbyapp.com/open/loan/not-a-number/2",
            "https://libbyapp.com/open/loan/1/2/extra",
            "https://user:password@libbyapp.com/open/loan/1/2",
            "https://libbyapp.com:444/open/loan/1/2",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_loan({"url": url})

    def test_rejects_nontext_fields(self):
        with self.assertRaises(ValueError):
            validate_loan({"url": "https://libbyapp.com/open/loan/1/2", "title": {"secret": 1}})

    def test_rejects_oversize_url(self):
        with self.assertRaises(ValueError):
            validate_loan({"url": "https://libbyapp.com/open/loan/1/2?" + "x" * 2050})


if __name__ == "__main__":
    unittest.main()
