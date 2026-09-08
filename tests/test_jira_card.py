"""카드·문서가 읽는 Jira 덩이 (REQ-20260908-074) — 판정(differs)은 서버 한 곳이다.

실행: python3 tests/ jira_card
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


class JiraCard(unittest.TestCase):

    def setUp(self):
        self._root = os.environ.get("S9_ROOT")
        self.root = tempfile.mkdtemp(prefix="s9jcard-")
        os.environ["S9_ROOT"] = self.root
        name = "s9jcard_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        if self._root is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = self._root
        shutil.rmtree(self.root, ignore_errors=True)

    def test_d1_no_issue_means_an_empty_block(self):
        self.assertEqual(self.m.jira_card_block({"status": "open"}), {})
        self.assertEqual(self.m.jira_card_block({"status": "open", "jira": {}}), {})
        self.assertEqual(self.m.jira_card_block({"status": "open", "jira": "x"}), {})

    def test_d1_differs_is_judged_by_category(self):
        base = {"key": "MP1-7", "url": "u", "status": "In Progress",
                "status_category": "indeterminate", "pending": "", "last_error": "",
                "synced_at": "t"}
        same = self.m.jira_card_block({"status": "review", "jira": base})
        self.assertFalse(same["differs"], "review 와 In Progress 는 같은 카테고리다")
        diff = self.m.jira_card_block({"status": "done", "jira": base})
        self.assertTrue(diff["differs"])
        self.assertEqual(diff["key"], "MP1-7")
        unknown = self.m.jira_card_block({"status": "done", "jira": {**base, "status_category": ""}})
        self.assertFalse(unknown["differs"], "카테고리를 모르면 다르다고 말하지 않는다")

    def test_d1_pending_without_key_still_shows(self):
        b = self.m.jira_card_block({"status": "open", "jira": {"pending": "create", "last_error": "x"}})
        self.assertEqual((b["pending"], b["last_error"], b["key"], b["differs"]),
                         ("create", "x", "", False))
        self.assertNotIn("actor", b)

    def test_d1_catalog_row_carries_it(self):
        row = self.m.catalog_row({"id": "REQ-1", "type": "request", "status": "open",
                                  "jira": {"key": "MP1-1", "url": "u", "status": "To Do",
                                           "status_category": "new", "actor": "hong"}}, "/x")
        self.assertEqual(row["jira"]["key"], "MP1-1")
        self.assertNotIn("actor", row["jira"])
        self.assertFalse(row["jira"]["differs"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
