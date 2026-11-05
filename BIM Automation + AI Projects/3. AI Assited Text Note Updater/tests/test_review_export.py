import csv
import json
import os
import tempfile
import unittest

import helpers  # noqa: F401
import review_ui


def item(uid, old, final, decision, **kw):
    d = {"unique_id": uid, "element_id": int(uid[1:]), "sheet_number": "A1", "view_name": "V", "old_text": old,
         "new_text": final, "final_text": final, "status": "pending", "flags": [], "decision": decision}
    d.update(kw)
    return d


class ExportTests(unittest.TestCase):
    def test_only_approved_and_really_changed_notes_are_exported(self):
        folder = tempfile.mkdtemp()
        items = [item("u1", "Install anchors.", "Installed anchors.", "approved"),
                 item("u2", "TBC", "", "approved"),
                 item("u3", "Seal gaps.", "Sealed gaps.", "rejected"),
                 item("u4", "Paint walls.", "Painted walls.", None),
                 item("u5", "No change here.", "No change here.", "approved")]
        approved = review_ui._export(items, folder)
        self.assertEqual([(a["unique_id"], a["delete"]) for a in approved], [("u1", False), ("u2", True)])
        with open(os.path.join(folder, "approved.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), approved)
        with open(os.path.join(folder, "review_decisions.csv"), encoding="utf-8-sig") as f:
            self.assertEqual(len(list(csv.reader(f))), 6)         # header + all 5 notes

    def test_edited_text_is_exported_with_original_line_breaks(self):
        folder = tempfile.mkdtemp()
        it = item("u1", "One.\rTwo.", "One.\nTwo changed.", "approved")
        approved = review_ui._export([it], folder)
        self.assertEqual(approved[0]["new_text"], "One.\rTwo changed.")


if __name__ == "__main__":
    unittest.main()
