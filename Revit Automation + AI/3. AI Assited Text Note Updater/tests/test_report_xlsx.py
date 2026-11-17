import json
import os
import tempfile
import unittest
from unittest import mock

import helpers
import report_xlsx as rx

HEADER = ["Sheet number", "Element ID", "Original text", "New text", "Date of update"]


def appr(eid, sheet, old, new, delete=False):
    return {"unique_id": "u%s" % eid, "element_id": eid, "sheet_number": sheet, "old_text": old, "new_text": new, "delete": delete}


def log(items, folder, **kw):
    applied = {a["unique_id"]: ("Deleted" if a["delete"] else "Changed") for a in items}
    return rx.write_report(items, applied, out_folder=folder, **kw)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(tempfile.mkdtemp(), "nested", "Reports")   # does not exist yet
        self.path = os.path.join(self.dir, "Text_notes_update_report.xlsx")

    def rows(self):
        return helpers.read_xlsx(self.path)

    def test_creates_the_file_with_the_default_name_and_columns(self):
        path, added, replaced = log([appr(1001, "A402", "Install anchors.", "Installed anchors."),
                                     appr(1002, "A100", "TBC", "", True)], self.dir)
        self.assertEqual(path, self.path)
        self.assertEqual((added, replaced), (2, 0))
        rows = self.rows()
        self.assertEqual(rows[0], HEADER)
        by_id = {r[1]: r for r in rows[1:]}
        self.assertEqual(by_id["1001"][3], "Installed anchors.")
        self.assertEqual(by_id["1002"][3], "")                      # removed note: empty new text
        self.assertEqual([r[0] for r in rows[1:]], ["A100", "A402"])  # sorted by sheet number

    def test_only_notes_really_changed_are_logged(self):
        items = [appr(1, "A1", "a", "b"), appr(2, "A1", "c", "d")]
        rx.write_report(items, {"u1": "Changed", "u2": "Skipped - note was edited since extraction"}, out_folder=self.dir)
        self.assertEqual([r[1] for r in self.rows()[1:]], ["1"])

    def test_same_element_id_replaces_its_row_and_new_ids_are_added(self):
        log([appr(1001, "A402", "Install anchors.", "Installed anchors.")], self.dir)
        _, added, replaced = log([appr(1001, "A402", "Installed anchors.", "Installed 4 anchors."),
                                  appr(1003, "A101", "Seal gaps.", "Sealed gaps.")], self.dir)
        self.assertEqual((added, replaced), (1, 1))
        rows = self.rows()[1:]
        self.assertEqual(len(rows), 2)
        self.assertEqual({r[1]: r[3] for r in rows}, {"1001": "Installed 4 anchors.", "1003": "Sealed gaps."})

    def test_duplicate_element_ids_in_one_batch_collapse_to_one_row(self):
        log([appr(5, "A9", "a", "b"), appr(5, "A9", "a", "c")], self.dir)
        rows = self.rows()[1:]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][3], "c")

    def test_nothing_changed_means_no_file(self):
        rx.write_report([appr(1, "A1", "a", "b")], {"u1": "Skipped - text note not found"}, out_folder=self.dir)
        self.assertFalse(os.path.exists(self.path))

    def test_planned_path_creates_nothing(self):
        self.assertEqual(rx.planned_path(out_folder=self.dir), self.path)
        self.assertFalse(os.path.exists(self.dir))

    def test_explicit_xlsx_path_is_used(self):
        target = os.path.join(self.dir, "custom name.xlsx")
        self.assertEqual(log([appr(1, "A1", "a", "b")], target)[0], target)
        self.assertTrue(os.path.exists(target))

    def test_folder_comes_from_results_json_when_not_given(self):
        scripts = tempfile.mkdtemp()
        out = os.path.join(scripts, "from_meta")
        results = os.path.join(scripts, "results.json")
        with open(results, "w") as f:
            json.dump({"meta": {"report_folder": out}, "items": []}, f)
        path, _, _ = rx.write_report([appr(1, "A1", "a", "b")], {"u1": "Changed"}, results_path=results)
        self.assertEqual(path, os.path.join(out, "Text_notes_update_report.xlsx"))

    def test_locked_file_keeps_rows_in_a_pending_file_and_adds_them_next_time(self):
        scripts = tempfile.mkdtemp()
        results = os.path.join(scripts, "results.json")
        with open(results, "w") as f:
            json.dump({"meta": {}, "items": []}, f)
        real = os.replace

        def locked(src, dst):
            if str(dst).endswith(".xlsx"):
                raise PermissionError("locked")
            return real(src, dst)

        with mock.patch("os.replace", locked):
            with self.assertRaises(Exception) as ctx:
                rx.write_report([appr(1, "A1", "a", "b")], {"u1": "Changed"}, results_path=results, out_folder=self.dir)
        self.assertIn("pending_report_rows.json", str(ctx.exception))
        self.assertTrue(os.path.exists(os.path.join(scripts, "pending_report_rows.json")))
        rx.write_report([appr(2, "A2", "c", "d")], {"u2": "Changed"}, results_path=results, out_folder=self.dir)
        self.assertEqual(sorted(r[1] for r in self.rows()[1:]), ["1", "2"])
        self.assertFalse(os.path.exists(os.path.join(scripts, "pending_report_rows.json")))

    def test_file_resaved_by_excel_keeps_user_edits(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl not installed")
        log([appr(1001, "A402", "Install anchors.", "Installed anchors."), appr(1002, "A100", "TBC", "", True)], self.dir)
        wb = openpyxl.load_workbook(self.path)
        ws = wb.active
        ws["F1"], ws["F2"] = "My comment", "checked by me"
        for r in range(2, ws.max_row + 1):
            ws.cell(r, 2).value = int(ws.cell(r, 2).value)       # Excel keeps ids as numbers
        wb.create_sheet("Notes")["A1"] = "keep me"
        wb.save(self.path)
        _, added, replaced = log([appr(1002, "A100", "Door TBC", "Door"), appr(1006, "A7", "x", "y")], self.dir)
        self.assertEqual((added, replaced), (1, 1))
        wb = openpyxl.load_workbook(self.path)
        self.assertEqual(wb.sheetnames[1], "Notes")
        ws = wb.active
        self.assertEqual(ws["F1"].value, "My comment")
        self.assertEqual(ws.max_row, 4)                           # header + 3 distinct element ids
        self.assertEqual(sorted(str(r[1]) for r in ws.iter_rows(min_row=2, values_only=True)), ["1001", "1002", "1006"])


if __name__ == "__main__":
    unittest.main()
