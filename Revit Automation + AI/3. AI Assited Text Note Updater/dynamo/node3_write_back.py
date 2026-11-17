# Dynamo Python Script node (engine: CPython3, Revit 2025). Paste this whole file into the node.
# The other files in tool/ must sit in the folder you connect to the node (see ../README.md).

# ======================================================================
# NODE 3: WRITE BACK TO REVIT   (2 inputs, 3rd optional)
# IN[0] approved.json path - wire it to the OUTPUT OF NODE 2 (not a list)
# IN[1] Boolean: False = dry run (only logs what WOULD happen, default), True = apply the changes
# IN[2] (optional) report output folder, only if it must differ from the one given to Node 1
# What it does:  1. replaces the text of every approved note
#                2. deletes notes whose words were ALL removed (Revit does not allow an empty text note)
#                3. adds ONLY the notes that were really changed / deleted to "Text_notes_update_report.xlsx"
#                   (sheet number, Element ID, original text, new text - empty if removed, date of update).
#                   One row per Element ID: an Element ID already in the file has its row REPLACED,
#                   new Element IDs go at the bottom. Nothing is written on a dry run
#                   (the dry run only shows where the report will be saved).
# OUT = [summary, report path, one log line per note]  -> connect a Watch node
#       if something goes wrong OUT = ["NODE 3 ERROR", the full error with its line number] instead
# ======================================================================
import clr
clr.AddReference("RevitServices")
clr.AddReference("RevitAPI")
import os, json, importlib.util, traceback
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager
from Autodesk.Revit.DB import TextNote


def one(x):  # Dynamo sometimes hands a single value over as a one-item list
    while isinstance(x, (list, tuple)) and len(x) == 1:
        x = x[0]
    return x


try:
    approved_path = one(IN[0])
    if not isinstance(approved_path, str) or not os.path.isfile(approved_path):
        raise Exception("IN[0] must be the approved.json path coming from Node 2 (got %r). "
                        "Run Node 2 first and wire its output here." % (approved_path,))
    folder = os.path.dirname(approved_path)
    apply_changes = bool(one(IN[1])) if len(IN) > 1 else False
    out_folder = one(IN[2]) if len(IN) > 2 else None
    out_folder = out_folder if isinstance(out_folder, str) and out_folder.strip() else None
    doc = DocumentManager.Instance.CurrentDBDocument
    norm = lambda t: str(t or "").replace("\r\n", "\n").replace("\r", "\n").strip()

    with open(approved_path, encoding="utf-8") as f:
        approved = json.load(f)

    applied, log = {}, []
    count = {"changed": 0, "deleted": 0, "skipped": 0}
    TransactionManager.Instance.EnsureInTransaction(doc)
    try:
        for a in approved:
            uid = a.get("unique_id")
            tag = "%s | %s" % (a.get("sheet_number", ""), str(uid)[:8])
            try:
                el = doc.GetElement(str(uid)) if uid else None
                if el is None or not isinstance(el, TextNote):
                    applied[uid], count["skipped"] = "Skipped - text note not found", count["skipped"] + 1
                elif norm(el.Text) != norm(a.get("old_text")):
                    applied[uid], count["skipped"] = "Skipped - note was edited since extraction", count["skipped"] + 1
                elif a.get("delete"):
                    if apply_changes:
                        doc.Delete(el.Id)
                    applied[uid] = "Deleted" if apply_changes else "Dry run - would delete"
                    count["deleted"] += 1
                else:
                    if apply_changes:
                        el.Text = a["new_text"]
                    applied[uid] = "Changed" if apply_changes else "Dry run - would change"
                    count["changed"] += 1
            except Exception as e:  # e.g. element owned by another user in a workshared model
                applied[uid], count["skipped"] = "Failed - %s" % e, count["skipped"] + 1
            log.append("%-28s %s | %s" % (applied[uid], tag, norm(a.get("old_text"))[:45].replace("\n", " ")))
    finally:
        TransactionManager.Instance.TransactionTaskDone()

    results_file = os.path.join(folder, "results.json")
    spec = importlib.util.spec_from_file_location("report_xlsx", os.path.join(folder, "report_xlsx.py"))
    rx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rx)
    if not apply_changes:
        report = "DRY RUN - no report written. After you apply (Boolean = True) it will be: %s" % rx.planned_path(results_file, out_folder=out_folder)
    else:
        try:
            path, added, replaced = rx.write_report(approved, applied, results_path=results_file, out_folder=out_folder)
            report = "%s (%d rows added, %d existing rows replaced)" % (path, added, replaced) if added + replaced else "no rows to add - nothing was changed in the model (report: %s)" % path
        except Exception as e:
            report = "REPORT FAILED (the model changes WERE applied): %s" % e

    mode = "APPLIED" if apply_changes else "DRY RUN (nothing changed in Revit)"
    OUT = ["%s: %d approved - %d changed, %d deleted, %d skipped" % (
        mode, len(approved), count["changed"], count["deleted"], count["skipped"]), report] + log
except Exception:
    OUT = ["NODE 3 ERROR"] + traceback.format_exc().splitlines()
