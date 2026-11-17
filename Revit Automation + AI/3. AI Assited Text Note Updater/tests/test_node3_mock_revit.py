"""Runs the real dynamo/node3_write_back.py against a fake Revit document."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import helpers
import ollama_client as oc

NODE3 = os.path.join(helpers.DYNAMO, "node3_write_back.py")


def appr(uid, eid, sheet, old, new, delete=False):
    return {"unique_id": uid, "element_id": eid, "sheet_number": sheet, "old_text": old, "new_text": new, "delete": delete}


class Node3Tests(unittest.TestCase):
    def setUp(self):
        self.scripts = tempfile.mkdtemp()
        self.reports = os.path.join(tempfile.mkdtemp(), "Reports")
        shutil.copy(os.path.join(helpers.TOOL, "report_xlsx.py"), self.scripts)
        with open(os.path.join(self.scripts, "results.json"), "w") as f:
            json.dump({"meta": {"report_folder": self.reports}, "items": []}, f)
        self.approved_path = os.path.join(self.scripts, "approved.json")
        self.doc = helpers.FakeDoc({"u1": "Install anchors.", "u2": "Door type TBC on site.", "u3": "Someone edited this already"})
        with open(self.approved_path, "w") as f:
            json.dump([appr("u1", 1001, "A402", "Install anchors.", "Installed anchors."),
                       appr("u2", 1002, "A100", "Door type TBC on site.", "", True),
                       appr("u3", 1003, "A101", "Walls are rated.", "Walls were rated."),
                       appr("nope", 1004, "A9", "x", "y")], f)

    def run_node(self, *inputs):
        ns = {"IN": list(inputs)}
        with mock.patch.dict("sys.modules", helpers.fake_revit_modules(self.doc)):
            with open(NODE3, encoding="utf-8") as f:
                exec(compile(f.read(), NODE3, "exec"), ns)
        return ns["OUT"]

    def report_path(self):
        return os.path.join(self.reports, "Text_notes_update_report.xlsx")

    def test_dry_run_changes_nothing_and_shows_where_the_report_will_go(self):
        out = self.run_node(self.approved_path, False)
        self.assertIn("DRY RUN", out[0])
        self.assertIn(self.report_path(), out[1])
        self.assertEqual(self.doc.elements["u1"].Text, "Install anchors.")
        self.assertIn("u2", self.doc.elements)
        self.assertFalse(os.path.exists(self.report_path()))

    def test_apply_edits_deletes_skips_and_writes_the_report(self):
        out = self.run_node(self.approved_path, True)
        self.assertIn("1 changed, 1 deleted, 2 skipped", out[0])
        self.assertEqual(self.doc.elements["u1"].Text, "Installed anchors.")
        self.assertNotIn("u2", self.doc.elements)                         # all words removed -> note deleted
        self.assertEqual(self.doc.elements["u3"].Text, "Someone edited this already")   # edited since extraction: untouched
        rows = helpers.read_xlsx(self.report_path())
        self.assertEqual(sorted(r[1] for r in rows[1:]), ["1001", "1002"])
        self.assertEqual({r[1]: r[3] for r in rows[1:]}["1002"], "")

    def test_second_apply_does_not_duplicate_report_rows(self):
        self.run_node(self.approved_path, True)
        self.run_node(self.approved_path, True)    # notes already changed -> skipped, nothing new to log
        self.assertEqual(len(helpers.read_xlsx(self.report_path())) - 1, 2)

    def test_wrong_input_gives_a_clear_error(self):
        for bad in (None, [["u1"], ["text"], [False]], os.path.join(self.scripts, "missing.json")):
            out = self.run_node(bad, False)
            self.assertEqual(out[0], "NODE 3 ERROR")
            self.assertTrue(any("approved.json" in line for line in out))

    def test_path_wrapped_in_a_one_item_list_is_accepted(self):
        self.assertIn("DRY RUN", self.run_node([self.approved_path], False)[0])


if __name__ == "__main__":
    unittest.main()
