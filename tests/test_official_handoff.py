"""Offline tests for the official ACSM -> Adobe Digital Editions helper.

No ebook content is downloaded and Adobe Digital Editions is not launched.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from official_epub_handoff import acsm_files, open_in_ade


class OfficialHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def test_only_local_acsm_files_detected(self):
        (self.folder / "book.acsm").write_text("fixture", encoding="utf-8")
        (self.folder / "other.EPUB").write_text("fixture", encoding="utf-8")
        (self.folder / "ignore.txt").write_text("fixture", encoding="utf-8")
        self.assertEqual([p.name for p in acsm_files(self.folder)], ["book.acsm"])

    def test_case_insensitive_extension(self):
        path = self.folder / "book.ACSM"
        path.write_text("test", encoding="utf-8")
        self.assertEqual(acsm_files(self.folder), [path])
        open_in_ade(path, dry_run=True)

    def test_newest_first(self):
        older = self.folder / "old.acsm"
        newer = self.folder / "new.acsm"
        older.write_text("test", encoding="utf-8")
        newer.write_text("test", encoding="utf-8")
        os.utime(older, (1000000000, 1000000000))
        os.utime(newer, (1100000000, 1100000000))
        self.assertEqual(acsm_files(self.folder), [newer, older])

    def test_missing_or_non_acsm_rejected(self):
        with self.assertRaises(ValueError):
            open_in_ade(self.folder / "missing.acsm", dry_run=True)
        path = self.folder / "book.epub"
        path.write_text("no", encoding="utf-8")
        with self.assertRaises(ValueError):
            open_in_ade(path, dry_run=True)

    def test_empty_acsm_rejected(self):
        path = self.folder / "empty.acsm"
        path.touch()
        with self.assertRaises(ValueError):
            open_in_ade(path, dry_run=True)


if __name__ == "__main__":
    unittest.main()
