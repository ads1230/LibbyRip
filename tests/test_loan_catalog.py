"""Offline checks for explicit ACSM-to-loan association.

No file is downloaded and Adobe Digital Editions is not launched.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import libby_handoff_server as bridge
import loan_catalog as catalog

LOAN1 = "https://libbyapp.com/open/loan/100/200"
LOAN2 = "https://libbyapp.com/open/loan/100/201"


class LoanCatalogTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        folder = Path(self.work.name)
        self.links = folder / "links.json"
        self.loans = folder / "loans.json"
        self.folder = folder
        self.loans.write_text(json.dumps([
            {"url": LOAN1, "title": "First", "author": "Author"},
            {"url": LOAN2, "title": "Second", "author": "Other"}
        ]), encoding="utf-8")
        for module, name, value in (
            (bridge, "LOANS_FILE", self.loans),
            (catalog, "LINKS_FILE", self.links),
        ):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def fixture(self, name="item.acsm", content="official fixture"):
        p = self.folder / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_initial_status_awaits_official_file(self):
        self.assertEqual([x["status"] for x in catalog.status()],
                         ["awaiting_official_acsm"] * 2)

    def test_explicit_link_and_verification(self):
        path = self.fixture()
        record = catalog.link(LOAN1, path)
        self.assertEqual(record["filename"], "item.acsm")
        self.assertEqual(catalog.verified_path(LOAN1), path.resolve())
        statuses = {x["url"]: x["status"] for x in catalog.status()}
        self.assertEqual(statuses[LOAN1], "official_acsm_linked")
        self.assertEqual(statuses[LOAN2], "awaiting_official_acsm")

    def test_prevent_accidental_assignment_to_two_loans(self):
        path = self.fixture()
        catalog.link(LOAN1, path)
        with self.assertRaisesRegex(ValueError, "already assigned"):
            catalog.link(LOAN2, path)

    def test_requires_transferred_loan(self):
        with self.assertRaisesRegex(ValueError, "transferred"):
            catalog.link("https://libbyapp.com/open/loan/123/999", self.fixture())

    def test_no_silent_file_replacement(self):
        catalog.link(LOAN1, self.fixture())
        other = self.fixture("other.acsm", "different")
        with self.assertRaisesRegex(ValueError, "already has"):
            catalog.link(LOAN1, other)
        self.assertEqual(catalog.link(LOAN1, other, replace=True)["filename"],
                         "other.acsm")

    def test_modified_file_detected(self):
        p = self.fixture()
        catalog.link(LOAN1, p)
        p.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"):
            catalog.verified_path(LOAN1)
        self.assertEqual(catalog.status()[0]["status"], "linked_file_missing_or_changed")

    def test_rejects_symlinks(self):
        original = self.fixture()
        symlink = self.folder / "alias.acsm"
        symlink.symlink_to(original)
        with self.assertRaisesRegex(ValueError, "regular"):
            catalog.link(LOAN1, symlink)

    def test_scan_lists_only_candidates_without_associating(self):
        self.fixture("mine.ACSM")
        self.fixture("not-an-acsm.txt")
        self.assertEqual(catalog.scan(self.folder), ["mine.ACSM"])
        self.assertEqual(catalog.status()[0]["status"], "awaiting_official_acsm")
        self.assertFalse(self.links.exists())


if __name__ == "__main__":
    unittest.main()
