"""Shared test helpers: import paths, a tiny .xlsx reader and a fake Revit/Dynamo environment."""
import os
import sys
import types
import zipfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tool")
DYNAMO = os.path.join(ROOT, "dynamo")
if TOOL not in sys.path:
    sys.path.insert(0, TOOL)

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def read_xlsx(path):
    """Rows of the FIRST sheet as lists of text (standard library only; handles shared and inline strings)."""
    q = lambda t: "{%s}%s" % (NS, t)
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ["".join(t.text or "" for t in si.iter(q("t")))
                      for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(q("si"))]
        sheet = next(ET.fromstring(z.read("xl/workbook.xml")).iter(q("sheet")))
        target = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        t = target[sheet.get("{%s}id" % RNS)].lstrip("/")
        root = ET.fromstring(z.read(t if t.startswith("xl/") else "xl/" + t))
        rows = []
        for row in root.iter(q("row")):
            cells = {}
            for c in row.findall(q("c")):
                col = ord(c.get("r")[0]) - 65
                v = c.find(q("v"))
                if c.get("t") == "s" and v is not None:
                    cells[col] = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    cells[col] = "".join(x.text or "" for x in c.iter(q("t")))
                else:
                    cells[col] = v.text if v is not None and v.text else ""
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
        return rows


class FakeTextNote:
    def __init__(self, uid, text):
        self.UniqueId, self.Text, self.Id = uid, text, uid


class FakeDoc:
    """Stands in for the Revit document: GetElement(uniqueId) and Delete(id)."""
    def __init__(self, notes):
        self.elements = {uid: FakeTextNote(uid, text) for uid, text in notes.items()}

    def GetElement(self, uid):
        return self.elements.get(uid)

    def Delete(self, element_id):
        self.elements.pop(element_id)


def fake_revit_modules(doc):
    """sys.modules entries that let a Dynamo node script run outside Revit."""
    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        return m
    tm = types.SimpleNamespace(EnsureInTransaction=lambda d: None, TransactionTaskDone=lambda: None)
    return {
        "clr": mod("clr", AddReference=lambda n: None),
        "RevitServices": mod("RevitServices"),
        "RevitServices.Persistence": mod("RevitServices.Persistence", DocumentManager=types.SimpleNamespace(
            Instance=types.SimpleNamespace(CurrentDBDocument=doc))),
        "RevitServices.Transactions": mod("RevitServices.Transactions", TransactionManager=types.SimpleNamespace(Instance=tm)),
        "Autodesk": mod("Autodesk"),
        "Autodesk.Revit": mod("Autodesk.Revit"),
        "Autodesk.Revit.DB": mod("Autodesk.Revit.DB", TextNote=FakeTextNote),
    }
