"""Excel report of the text notes that were ACTUALLY changed in the Revit model. Standard library only, so it
runs inside Dynamo's Python (no openpyxl needed).

Called by the write-back node (Node 3) after the changes were applied - never by the review screen:

    write_report(approved, applied, results_path=None, out_path=None, out_folder=None) -> (path, rows_added, rows_replaced)

  approved   : the list read from approved.json
  applied    : {unique_id: "Changed" | "Deleted" | "Skipped - ..." | "Failed - ..."} from the write-back node;
               only "Changed" and "Deleted" notes are logged
  out_folder : report folder (else the folder given to Node 1, stored in results.json, else the scripts folder)

File: "Text_notes_update_report.xlsx" with the columns
      Sheet number | Element ID | Original text | New text (empty if the note was removed) | Date of update
The file is never renamed or recreated: if it does not exist it is created, if it exists it is updated in place
(its formatting, other sheets and extra columns you added stay as they are).
One row per Element ID: if the Element ID is already in the report, that row is REPLACED with the newest values;
otherwise the row is added at the bottom. So the same file keeps updating and never holds duplicate Element IDs.
If the file cannot be written (for example it is open in Excel) the rows are kept in pending_report_rows.json
next to the scripts and added automatically the next time.
"""
import json, os, re, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from xml.sax.saxutils import escape
from xml.sax.saxutils import escape

_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
HEAD, BODY, GREEN, RED, AMBER, GREY = 1, 2, 3, 4, 5, 6   # cell style ids (see _STYLES)

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _fill(rgb):
    return '<fill><patternFill patternType="solid"><fgColor rgb="%s"/><bgColor indexed="64"/></patternFill></fill>' % rgb


def _xf(font, fill, align):
    return ('<xf numFmtId="0" fontId="%d" fillId="%d" borderId="1" xfId="0" applyFont="1" applyFill="1" '
            'applyBorder="1" applyAlignment="1"><alignment vertical="%s" wrapText="1"/></xf>' % (font, fill, align))


_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="%s">' % _NS +
    '<fonts count="2"><font><sz val="10"/><name val="Arial"/></font>'
    '<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font></fonts>'
    '<fills count="8"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
    + _fill("FF1F3A5F") + _fill("FFDFF3E3") + _fill("FFF8D7DA") + _fill("FFFFF3CD") + _fill("FFEDEDED") +
    '</fills><borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
    '<border><left style="thin"><color rgb="FFD0D0D0"/></left><right style="thin"><color rgb="FFD0D0D0"/></right>'
    '<top style="thin"><color rgb="FFD0D0D0"/></top><bottom style="thin"><color rgb="FFD0D0D0"/></bottom><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="7"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    + _xf(1, 2, "center") + _xf(0, 0, "top") + _xf(0, 3, "top") + _xf(0, 4, "top") + _xf(0, 5, "top") + _xf(0, 6, "top") +
    '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def _text(v):
    return _BAD.sub("", "" if v is None else str(v)).replace("\r\n", "\n").replace("\r", "\n")


def _sheet_xml(header, rows, widths, style_col, style_fn):
    n = len(header)
    if not rows:
        rows = [["(nothing to show)"] + [""] * (n - 1)]
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="%s">' % _NS,
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>',
           '<sheetFormatPr defaultRowHeight="15"/><cols>']
    out += ['<col min="%d" max="%d" width="%s" customWidth="1"/>' % (i, i, w) for i, w in enumerate(widths, 1)]
    out.append("</cols><sheetData>")
    for r, vals in enumerate([header] + rows, 1):
        out.append('<row r="%d">' % r)
        for c, v in enumerate(vals):
            style = HEAD if r == 1 else (style_fn(vals[style_col]) if c == style_col else BODY)
            out.append('<c r="%s%d" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                       % (chr(65 + c), r, style, escape(_text(v))))
        out.append("</row>")
    out.append('</sheetData><autoFilter ref="A1:%s%d"/></worksheet>' % (chr(64 + n), len(rows) + 1))
    return "".join(out)


def _save(path, sheets):
    tmp = path + ".tmp"
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          + "".join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i
                    for i in range(1, len(sheets) + 1)) + "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="%s" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' % _NS
          + "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(s[0]), i, i) for i, s in enumerate(sheets, 1))
          + "</sheets></workbook>")
    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              + "".join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i, i)
                        for i in range(1, len(sheets) + 1))
              + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' % (len(sheets) + 1))
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbrels)
        z.writestr("xl/styles.xml", _STYLES)
        for i, s in enumerate(sheets, 1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, _sheet_xml(*s[1:]))
    try:
        os.replace(tmp, path)
    except PermissionError:
        os.remove(tmp)
        raise Exception("Cannot write %s - close it in Excel and run again." % path)


_RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _norm_id(v):
    t = _text(v).strip()
    return re.sub(r"\.0+$", "", t) if re.fullmatch(r"\d+\.0+", t) else t


def _dedupe(rows):
    """One row per Element ID inside a batch (the last one wins)."""
    out = {}
    for i, r in enumerate(rows):
        out[_norm_id(r[1]) or ("row", i)] = r
    return list(out.values())


def _update_workbook(path, rows):
    """Edit the existing workbook in place: rows whose Element ID is already there are replaced, the others are added
    at the bottom. Only the sheet XML is touched; everything else is copied unchanged. Returns (added, replaced)."""
    q = lambda t: "{%s}%s" % (_NS, t)
    with zipfile.ZipFile(path) as zin:
        wb = ET.fromstring(zin.read("xl/workbook.xml"))
        target = {r.get("Id"): r.get("Target") for r in ET.fromstring(zin.read("xl/_rels/workbook.xml.rels"))}
        sheets = list(wb.iter(q("sheet")))
        pick = next((x for x in sheets if x.get("name") == SHEET), sheets[0])
        t = target[pick.get("{%s}id" % _RNS)].lstrip("/")
        sheet_file = t if t.startswith("xl/") else "xl/" + t
        raw = zin.read(sheet_file)
        xml = raw.decode("utf-8")
        ours = zin.read("xl/styles.xml") == _STYLES.encode("utf-8")
        shared = []
        if "xl/sharedStrings.xml" in zin.namelist():
            shared = ["".join(x.text or "" for x in si.iter(q("t")))
                      for si in ET.fromstring(zin.read("xl/sharedStrings.xml")).iter(q("si"))]
        # Element ID (column B) -> row number of its existing row (the latest one if there are several)
        where, last = {}, 0
        for row in ET.fromstring(raw).iter(q("row")):
            n = int(row.get("r"))
            last = max(last, n)
            for c in row.findall(q("c")):
                if re.fullmatch(r"B\d+", c.get("r", "")):
                    v, kind = c.find(q("v")), c.get("t")
                    val = (shared[int(v.text)] if kind == "s" and v is not None else
                           "".join(x.text or "" for x in c.iter(q("t"))) if kind == "inlineStr" else
                           (v.text if v is not None and v.text else ""))
                    val = _norm_id(val)
                    if val and val != "Element ID":
                        where[val] = n
        if last == 0 or "</sheetData>" not in xml:
            raise ValueError("unexpected sheet layout")

        def cells(n, vals, styles):
            out = []
            for c, v in enumerate(vals):
                col = chr(65 + c)
                sid = (RED if (c == 3 and not _text(v)) else BODY) if ours else styles.get(col)
                out.append('<c r="%s%d"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                           % (col, n, ' s="%s"' % sid if sid is not None else "", escape(_text(v))))
            return "".join(out)

        # new rows copy the look of the last existing row, column by column (only needed when the file is not ours)
        tail = re.findall(r'<row r="%d"[^>]*>(.*?)</row>' % last, xml, re.S)
        tail_styles = {c[0]: c[1] for c in re.findall(r'<c r="([A-Z]+)\d+"[^>]*? s="(\d+)"', tail[0])} if tail else {}
        added = replaced = 0
        appended = []
        for vals in rows:
            key = _norm_id(vals[1])
            n = where.get(key) if key else None
            m = re.search(r'<row r="%d"([^>]*?)(/>|>(.*?)</row>)' % n, xml, re.S) if n else None
            if m:  # replace columns A-E of the existing row, keep any other column (your own notes) as it is
                inner = m.group(3) or ""
                styles = {c[0]: c[1] for c in re.findall(r'<c r="([A-E])%d"[^>]*? s="(\d+)"' % n, inner)}
                rest = re.sub(r'<c r="[A-E]%d"(?:[^>]*/>|[^>]*>.*?</c>)' % n, "", inner, flags=re.S)
                attrs = re.sub(r'\s+spans="[^"]*"', "", m.group(1))
                xml = xml[:m.start()] + '<row r="%d"%s>%s%s</row>' % (n, attrs, cells(n, vals, styles), rest) + xml[m.end():]
                replaced += 1
            else:
                last += 1
                if key:
                    where[key] = last
                appended.append('<row r="%d">%s</row>' % (last, cells(last, vals, tail_styles)))
                added += 1
        if appended:
            xml = xml.replace("</sheetData>", "".join(appended) + "</sheetData>", 1)
        xml = re.sub(r'(<dimension ref="[A-Z]+\d+:[A-Z]+)\d+"', r'\g<1>%d"' % last, xml, count=1)
        xml = re.sub(r'(<autoFilter ref="[A-Z]+\d+:[A-Z]+)\d+"', r'\g<1>%d"' % last, xml, count=1)
        tmp = path + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                zout.writestr(item, xml.encode("utf-8") if item.filename == sheet_file else zin.read(item.filename))
    try:
        os.replace(tmp, path)
    except PermissionError:
        os.remove(tmp)
        raise Exception("Cannot write %s - close it in Excel and run again." % path)
    return added, replaced


def _sort_key(a):
    parts = re.split(r"(\d+)", str(a.get("sheet_number", "")).lower())
    return [int(p) if i % 2 else p for i, p in enumerate(parts)]


REPORT_NAME = "Text_notes_update_report.xlsx"
SHEET = "Text notes update report"
HEAD_ROW = ["Sheet number", "Element ID", "Original text", "New text", "Date of update"]


def _out_path(here, out_path, out_folder, meta, create=True):
    if out_path:
        if create:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        return out_path
    folder = out_folder or meta.get("report_folder") or here or os.getcwd()
    if isinstance(folder, (list, tuple)):
        folder = folder[0] if folder else (here or os.getcwd())
    folder = os.path.expandvars(os.path.expanduser(str(folder).strip())) or here or os.getcwd()
    if folder.lower().endswith(".xlsx"):  # a full file path was given
        if create:
            os.makedirs(os.path.dirname(os.path.abspath(folder)), exist_ok=True)
        return folder
    if create:
        os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, REPORT_NAME)


def _load_meta(results_path):
    here, meta = None, {}
    if results_path:
        here = os.path.dirname(os.path.abspath(results_path))
        try:
            with open(results_path, encoding="utf-8") as f:
                meta = json.load(f).get("meta", {})
        except Exception:
            pass
    return here, meta


def planned_path(results_path=None, out_path=None, out_folder=None):
    """Where the report will be saved - computed without creating anything (used by the dry run)."""
    here, meta = _load_meta(results_path)
    return _out_path(here, out_path, out_folder, meta, create=False)


def write_report(approved, applied, results_path=None, out_path=None, out_folder=None):
    here, meta = _load_meta(results_path)
    out = _out_path(here, out_path, out_folder, meta)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_rows = [[a.get("sheet_number"), a.get("element_id"), a["old_text"], "" if a.get("delete") else a["new_text"], now]
                for a in sorted(approved, key=_sort_key) if applied.get(a["unique_id"]) in ("Changed", "Deleted")]

    # rows that could not be written last time are added first (only if they belong to this same file)
    pend_path = os.path.join(here, "pending_report_rows.json") if here else None
    pending = {}
    if pend_path and os.path.exists(pend_path):
        try:
            with open(pend_path, encoding="utf-8") as f:
                pending = json.load(f)
        except Exception:
            pending = {}
    rows = _dedupe(pending.pop(out, []) + new_rows)   # one row per Element ID
    if not rows:
        return out, 0, 0

    try:
        rows = [[_text(v) for v in r] for r in rows]
        if os.path.exists(out):
            added, replaced = _update_workbook(out, rows)   # same file: replace by Element ID, else add at the bottom
        else:
            added, replaced = len(rows), 0
            _save(out, [(SHEET, HEAD_ROW, rows, [14, 12, 60, 60, 18], 3,
                         lambda v: RED if v == "" else BODY)])
    except Exception as e:
        if pend_path:  # keep the rows so the log does not lose them
            pending[out] = [[_text(v) for v in r] for r in rows]
            with open(pend_path, "w", encoding="utf-8") as f:
                json.dump(pending, f, indent=2, ensure_ascii=False)
        raise Exception("%s%s" % (e, " The %d row(s) were saved in pending_report_rows.json and will be added next time." % len(rows) if pend_path else ""))
    if pend_path and os.path.exists(pend_path):
        if pending:
            with open(pend_path, "w", encoding="utf-8") as f:
                json.dump(pending, f, indent=2, ensure_ascii=False)
        else:
            os.remove(pend_path)
    return out, added, replaced
