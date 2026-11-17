"""Dynamo -> Ollama bridge. Standard library only (works in Dynamo's CPython3 engine).

Only notes passing the "selection" rules in rules.json are sent to Ollama; the rest get status "skipped".
Notes in:  [{"unique_id","element_id","sheet_number","text", ...}]
Results out (results.json): {"meta": {...}, "items": [{..., "old_text","new_text","final_text",
                             "status": pending|flagged|unchanged, "flags": [...], "decision": null}]}
CLI: python ollama_client.py notes.json results.json
"""
import json, os, re, sys, urllib.request
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))


def load_rules(path=None):
    with open(path or os.path.join(HERE, "rules.json"), encoding="utf-8") as f:
        return json.load(f)


def build_system_prompt(cfg):
    lines = [cfg["task"], "", "Apply ONLY these rules:"]
    lines += ["%d. %s" % (i, r["instruction"])
              for i, r in enumerate([r for r in cfg["rules"] if r.get("enabled", True)], 1)]
    lines += ["", "Never change:"] + ["- " + x for x in cfg["never_change"]]
    lines += ["", "If nothing needs changing, return the text exactly as given.",
              'Reply with JSON only: {"new_text": "<rewritten note>"}']
    return "\n".join(lines)


def _post(url, payload, timeout):
    req = urllib.request.Request(url, json.dumps(payload).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check_ollama(cfg):
    try:
        with urllib.request.urlopen(cfg["ollama_url"] + "/api/tags", timeout=5) as r:
            names = [m["name"] for m in json.loads(r.read().decode("utf-8"))["models"]]
    except Exception as e:
        raise RuntimeError("Ollama not reachable at %s (%s). Start it with 'ollama serve'."
                           % (cfg["ollama_url"], e))
    want = cfg["model"]
    if not any(n == want or n.startswith(want + ":") for n in names):
        raise RuntimeError("Model '%s' not installed. Run: ollama pull %s" % (want, want))


def _messages(cfg, system, text):
    msgs = [{"role": "system", "content": system}]
    for ex in cfg.get("examples", []):  # worked examples as earlier chat turns
        msgs += [{"role": "user", "content": ex["input"]},
                 {"role": "assistant", "content": json.dumps({"new_text": ex["output"]})}]
    return msgs + [{"role": "user", "content": text}]


def rewrite(cfg, system, text):
    data = _post(cfg["ollama_url"] + "/api/chat", {
        "model": cfg["model"], "stream": False, "format": "json",
        "options": {"temperature": cfg.get("temperature", 0), "seed": cfg.get("seed", 42), "num_ctx": 4096},
        "messages": _messages(cfg, system, text),
    }, cfg.get("timeout", 120))
    return json.loads(data["message"]["content"])["new_text"]


def _norm(t):
    return t.replace("\r\n", "\n").replace("\r", "\n")


def match_newlines(old, new):
    """Give `new` the same line-break style Revit used in `old`."""
    nl = "\r\n" if "\r\n" in old else ("\r" if "\r" in old else "\n")
    return _norm(new).replace("\n", nl)


_SEP = re.compile(r"(\r\n|\r|\n)")
_TOK = re.compile(r"\s+|\w+|[^\w\s]")


def _matcher(old, new):
    A, B = _TOK.findall(old), _TOK.findall(new)
    return A, B, SequenceMatcher(None, [t.lower() for t in A], [t.lower() for t in B], autojunk=False)


def restore_case(old, new):
    """Words the model kept but re-capitalised (Title Case -> lower case) get their original capitalisation back."""
    A, B, sm = _matcher(old, new)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            B[j1:j2] = A[i1:i2]
    return "".join(B)


# helper verbs that legitimately disappear or change when converting to past tense (is to be removed -> was removed)
_AUX = {"is", "am", "are", "be", "been", "being", "to", "has", "have", "does", "do", "will", "can",
        "was", "were", "had", "did", "would", "could"}


def _same(x, y):
    """True if y looks like an inflected form of x (Provide/Provided), i.e. reworded rather than removed."""
    x, y = x.lower(), y.lower()
    if len(x) < 3 or len(y) < 3:
        return False
    c = 0
    while c < min(len(x), len(y)) and x[c] == y[c]:
        c += 1
    return c >= max(3, min(len(x), len(y)) - 2)


def removed_chunks(old, new):
    """Text that was deleted outright (not merely reworded)."""
    A, B, sm = _matcher(old, new)
    chunks = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag not in ("delete", "replace"):
            continue
        d, ins, used, cur = A[i1:i2], [t for t in B[j1:j2] if not t.isspace()], set(), ""
        for t in d:
            m = None if t.isspace() else next((q for q, y in enumerate(ins) if q not in used and _same(t, y)), None)
            if m is None:
                cur += t
            else:
                used.add(m)
                if cur.strip():
                    chunks.append(cur.strip())
                cur = ""
        if cur.strip():
            chunks.append(cur.strip())
    return chunks


def looks_unrelated(old, new):
    """True if the model's answer shares (almost) nothing with the original line, e.g. it copied an example."""
    ow = re.findall(r"\w+", old.lower())
    nw = re.findall(r"\w+", new.lower())
    unknown = sum(1 for w in nw if w not in _AUX and not any(w == o or _same(o, w) or _same(w, o) for o in ow))
    return bool(nw) and unknown > max(1, 0.35 * len(nw))


def guard_removals(old, new, cfg, keep_case=True):
    """Rebuild the model's answer so that ONLY removal phrases (and helper verbs like 'is to be') can disappear.
    Anything else the model deleted - words, punctuation, '(Figure 2)' - is put back."""
    pats = cfg.get("selection", {}).get("always_select", [])

    def removable(text):
        t = text.strip()
        if not t:
            return True
        words = re.findall(r"\w+", t.lower())
        if words and set(words) <= _AUX:
            return True
        return any(_hit(p, t) for p in pats)

    A, B, sm = _matcher(old, new)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out += A[i1:i2] if keep_case else B[j1:j2]
        elif tag == "insert":
            out += B[j1:j2]
        elif tag == "delete":
            if not removable("".join(A[i1:i2])):
                out += A[i1:i2]
        else:  # replace: reworded words take the new form, other deleted text must be removable
            ins = B[j1:j2]
            words = [q for q, t in enumerate(ins) if not t.isspace()]
            used, run = set(), []

            def flush():
                if run and not removable("".join(run)):
                    out.extend(run)
                del run[:]

            for t in A[i1:i2]:
                m = None if t.isspace() else next((q for q in words if q not in used and _same(t, ins[q])), None)
                if m is None:
                    run.append(t)
                else:
                    flush()
                    used.add(m)
                    out.append(ins[m])
            flush()
            extra = [ins[q] for q in words if q not in used]
            if extra:
                out.append(" ".join(extra))
    text = "".join(out)
    if "  " not in old:
        text = re.sub(r"[ \t]{2,}", " ", text)
    if not re.search(r"\s[.,;:]", old):
        text = re.sub(r"[ \t]+([.,;:])", r"\1", text)
    return text


def enforce(text, cfg):
    """Deterministic safety net for verbs small models often skip (is -> was, are -> were ...)."""
    fr = cfg.get("forced_replacements", {})
    m = fr.get("map", {})
    if not fr.get("enabled", False) or not m:
        return text
    pat = re.compile(r"\b(%s)\b" % "|".join(re.escape(k) for k in sorted(m, key=len, reverse=True)), re.I)

    def sub(mo):
        w, r = mo.group(1), m[mo.group(1).lower()]
        return r.upper() if w.isupper() and len(w) > 1 else (r.capitalize() if w[0].isupper() else r)
    return pat.sub(sub, text)


def rewrite_note(cfg, system, note, cache):
    """Send each line of the note to Ollama separately so line breaks, blank lines and spacing are never lost.
    Lines that fail the selection rules are kept as they are. Returns (new_text, flags)."""
    old, flags, out = note["text"], [], []
    parts = _SEP.split(old)  # text, separator, text, separator, ...
    keep_case = cfg.get("preserve_case", True) and not any(
        r["id"] == "sentence_case" and r.get("enabled") for r in cfg["rules"])
    for k in range(0, len(parts), 2):
        text, sep, new = parts[k], (parts[k + 1] if k + 1 < len(parts) else ""), parts[k]
        core = text.strip()
        if core and skip_reason(dict(note, text=core), cfg) is None:
            if core not in cache:  # identical lines are only sent once
                try:
                    cache[core] = (rewrite(cfg, system, core), None)
                except Exception as e:
                    cache[core] = (core, "Ollama error: %s" % e)
            res, err = cache[core]
            if err:
                flags.append(err)
                res = core
            elif res.strip() and looks_unrelated(core, res):
                flags.append("Model answer ignored (unrelated to the original): '%s'" % core[:50])
                res = core
            res = enforce(guard_removals(core, res, cfg, keep_case), cfg)
            if not res.strip():
                continue  # whole line removed: drop it together with its line break
            new = text[:len(text) - len(text.lstrip())] + res.strip() + text[len(text.rstrip()):]
        out.append(new + sep)
    result = "".join(out)
    if not re.search(r"[\r\n]$", old):
        result = result.rstrip("\r\n")
    return result, list(dict.fromkeys(flags))


def validate(old, new, cfg):
    v, flags = cfg.get("validation", {}), []
    o, n = _norm(old), _norm(new)
    if not n.strip():
        return ["Whole note removed - approving will delete this note"]
    if o.count("\n") != n.count("\n"):
        flags.append("Line break count changed")
    po, pn = Counter(), Counter()
    for p in cfg.get("protected_patterns", []):
        po.update(re.findall(p, o)); pn.update(re.findall(p, n))
    allowed = set(t.upper() for t in cfg.get("allow_removed_tokens", []))
    lost = Counter({k: c for k, c in (po - pn).items() if k.upper() not in allowed})
    changed = lost + (pn - po)
    if changed:
        flags.append("Protected text changed: " + ", ".join(sorted(set(changed.elements()))))
    ratio = len(n) / max(len(o), 1)
    if not v.get("min_length_ratio", 0) <= ratio <= v.get("max_length_ratio", 99):
        flags.append("Length changed a lot (x%.2f)" % ratio)
    if cfg.get("check_removals", True):
        pats = cfg.get("selection", {}).get("always_select", [])
        for chunk in removed_chunks(o, n):
            words = re.findall(r"\w+", chunk.lower())
            if words and not set(words) <= _AUX and not any(_hit(p, chunk) for p in pats):
                flags.append("Removed text that is not a removal phrase: '%s'" % chunk[:60])
    wo, wn = re.findall(r"\w+", o.lower()), re.findall(r"\w+", n.lower())
    if len(wo) >= v.get("min_words_for_change_check", 8) and \
            1 - SequenceMatcher(None, wo, wn).ratio() > v.get("max_changed_word_ratio", 1):
        flags.append("Too many words changed")
    return flags


def _hit(p, text):
    return re.search(p["pattern"], text, re.I if "i" in p.get("flags", "") else 0)


def skip_reason(note, cfg):
    """Return None if the note should go to Ollama, otherwise why it is skipped."""
    s = cfg.get("selection", {})
    text, sheet = note["text"].strip(), str(note.get("sheet_number", ""))
    if not text:
        return "empty note"
    if not s.get("enabled", True):
        return None
    inc = s.get("sheet_include", [])
    if inc and not any(re.search(p, sheet) for p in inc):
        return "sheet not in sheet_include"
    if any(re.search(p, sheet) for p in s.get("sheet_exclude", [])):
        return "sheet in sheet_exclude"
    if any(_hit(p, text) for p in s.get("always_select", [])):
        return None  # contains a phrase that must be removed: bypasses the checks below
    if len(text.split()) < s.get("min_words", 1):
        return "fewer than %d words" % s["min_words"]
    if len(text) > s.get("max_chars", 10 ** 9):
        return "longer than %d characters" % s["max_chars"]
    for p in s.get("skip_patterns", []):
        if _hit(p, text):
            return "skip rule '%s'" % p["id"]
    req = s.get("require_any", [])
    if req and not any(_hit(p, text) for p in req):
        return "no require_any trigger found"
    return None


def preview(notes, rules_path=None):
    """Dry run: show which notes WOULD be sent to Ollama. No model needed - use it to tune the selection rules."""
    cfg = load_rules(rules_path)
    out = [(n.get("sheet_number", ""), skip_reason(n, cfg), n["text"]) for n in notes]
    for sheet, why, text in out:
        print("%-8s %-38s %s" % (sheet, "SELECTED" if not why else "skip: " + why, text.replace("\n", " ")[:60]))
    print("%d selected, %d skipped" % (sum(1 for o in out if not o[1]), sum(1 for o in out if o[1])))
    return out


def run(notes, rules_path=None, out_path=None, progress=print, report_folder=None):
    """report_folder: where the cumulative Excel log is saved (stored in results.json, used by the later nodes)."""
    if isinstance(report_folder, (list, tuple)):
        report_folder = report_folder[0] if report_folder else None
    report_folder = (report_folder or "").strip()
    if report_folder:  # fail now, not after the slow model run
        target = os.path.expandvars(os.path.expanduser(report_folder))
        target = os.path.dirname(os.path.abspath(target)) if target.lower().endswith(".xlsx") else target
        try:
            os.makedirs(target, exist_ok=True)
        except Exception as e:
            raise Exception("Report output folder cannot be used: %s (%s)" % (report_folder, e))
    cfg = load_rules(rules_path)
    reasons = [skip_reason(n, cfg) for n in notes]
    if any(r is None for r in reasons):
        check_ollama(cfg)
    system, cache, items = build_system_prompt(cfg), {}, []
    for i, (n, why) in enumerate(zip(notes, reasons), 1):
        old = n["text"]
        item = {k: v for k, v in n.items() if k != "text"}
        if why:
            item.update(old_text=old, new_text=old, final_text=old, status="skipped",
                        skip_reason=why, flags=[], decision=None)
        else:
            new, flags = rewrite_note(cfg, system, n, cache)
            flags = flags + validate(old, new, cfg)
            status = "unchanged" if (new == old and not flags) else ("flagged" if flags else "pending")
            item.update(old_text=old, new_text=new, final_text=new, status=status,
                        skip_reason=None, flags=flags, decision=None)
        items.append(item)
        if progress:
            progress("[%d/%d] %s %s" % (i, len(notes), n.get("sheet_number", ""), item["status"]))
    doc = {"meta": {"model": cfg["model"], "created": datetime.now().isoformat(timespec="seconds"),
                    "rules": [r["id"] for r in cfg["rules"] if r.get("enabled", True)],
                    "selected": sum(1 for r in reasons if not r), "skipped": sum(1 for r in reasons if r),
                    "report_folder": report_folder},
           "items": items}
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
    return doc


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("usage: python ollama_client.py notes.json [results.json] [--dry-run]")
    with open(args[0], encoding="utf-8") as f:
        _notes = json.load(f)
    if "--dry-run" in sys.argv:
        preview(_notes)
    else:
        run(_notes, out_path=args[1] if len(args) > 1 else os.path.join(os.path.dirname(os.path.abspath(args[0])), "results.json"))
