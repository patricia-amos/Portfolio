# Revit As-Built Text Note Cleanup

AI-assisted clean-up of text notes on Revit sheets. A local language model suggests the new wording, a person approves every change, Dynamo writes the approved text back into the model, and an Excel log records what changed. Everything runs on your own computer.

## The problem

Drawing sets keep wording written for the construction phase: *"Contractor to verify dimensions on site"*, *"Install anchors as required"*, *"Door type TBC"*. Once the building is built these notes are out of date: nothing is pending any more, and the tense is still future or imperative. Fixing them by hand across many sheets is slow and error-prone.

## What it does

| Original | Result |
|---|---|
| Install anchors as required. | Installed anchors. |
| Contractor to verify dimensions on site. | *(note deleted: nothing meaningful is left)* |
| Architect to provide final colour. Paint walls. | Painted walls. |
| Walls are 2 hr rated and the door is fire-rated. | Walls were 2 hr rated and the door was fire-rated. |
| Existing partition is to be removed. | Existing partition was removed. |
| See detail 3/A501 for connection. | *(unchanged: cross-reference)* |

## How it works

```
Dynamo extraction (your nodes) -> unique IDs, element IDs, sheet numbers, texts
                                          |
Node 1  tool/ollama_client.py     select applicable notes -> local model rewrites line by line
                                  -> guards repair or reject bad answers      -> results.json
                                          |
Node 2  tool/review_ui.py         browser review page: approve / reject / edit  -> approved.json
                                          |
Node 3  dynamo/node3_write_back   replace text, delete fully-removed notes
                                  -> tool/report_xlsx.py                        -> Excel log
```

1. **Select.** Rules decide which notes and lines are applicable (skip titles, dimensions and cross-references; require an action verb, a form of is/are/have/do, or a removal phrase). Skipped notes keep a reason.
2. **Rewrite.** Each line goes to a local [Ollama](https://ollama.com) model with temperature 0 and a fixed seed, using the rules in `tool/rules.json`.
3. **Guard.** The model's answer is never trusted blindly:
   - an answer unrelated to the original (for example a copied example) is rejected;
   - text deleted by the model that is not a removal phrase is put back;
   - Title Case and line breaks are restored;
   - `is`/`are`/`has`... are converted by a configurable word map as a safety net;
   - numbers, tags and acronyms are checked before and after; doubtful notes are flagged.
4. **Review.** A page on `127.0.0.1` shows old and new text with a colour-coded diff (yellow = reworded, red strikethrough = removed). Approve, reject or edit each note.
5. **Write back.** Dynamo replaces the text of approved notes and deletes notes whose words were all removed. A note edited in Revit since extraction is skipped.
6. **Report.** Changed notes are logged to `Text_notes_update_report.xlsx` (sheet number, Element ID, original text, new text, date of update). One row per Element ID: an existing row is replaced, a new ID is added at the bottom, and the file is updated in place.

## Requirements

- Revit 2025 with Dynamo (Python nodes set to the **CPython3** engine)
- [Ollama](https://ollama.com) running locally with a model pulled (default `llama3.1:8b`, set in `tool/rules.json`); developed with Ollama 0.40.2
- No pip packages. All Python uses the standard library, so it runs inside Dynamo's own Python. Python 3.9+ is only needed to run the command-line demo and the tests.

## Try it without Revit

```bash
git clone https://github.com/<you>/revit-textnote-asbuilt-cleanup.git
cd revit-textnote-asbuilt-cleanup

# 1. which sample notes would be sent to the model? (no model needed)
python tool/ollama_client.py samples/sample_notes.json --dry-run

# 2. rewrite them (needs Ollama running and: ollama pull llama3.1:8b)
python tool/ollama_client.py samples/sample_notes.json

# 3. open the review page, then click "Save & finish"
python tool/review_ui.py samples/results.json
```

On Windows use `py` instead of `python`. Output files (`results.json`, `approved.json`, `review_decisions.csv`) appear next to the sample file and are git-ignored.

## Use it in Dynamo

Put the four files in `tool/` into one folder, then paste each file from `dynamo/` into a Python Script node (CPython3). Full wiring is in [`dynamo/README.md`](dynamo/README.md). In short:

| Node | Inputs | Output |
|---|---|---|
| 1 `node1_ask_ollama.py` | scripts folder, unique IDs, element IDs, sheet numbers, texts, report folder | path to `results.json` |
| 2 `node2_review.py` | output of node 1 | path to `approved.json` (after you click Save & finish) |
| 3 `node3_write_back.py` | output of node 2, Boolean (False = dry run, True = apply) | log lines for a Watch node |

**Always run Node 3 as a dry run first (Boolean False), and test on a copy of the model.**

## Configuration (`tool/rules.json`)

| Key | What it controls |
|---|---|
| `model`, `ollama_url`, `temperature`, `seed` | which local model is used and how repeatable it is |
| `rules` | language rules in plain English, each with `enabled` (as required, pending input, past tense, ...) |
| `examples` | worked examples, sent to the model as earlier chat turns |
| `selection` | which notes are applicable: sheet include/exclude, skip patterns, required triggers, always-select removal phrases |
| `forced_replacements` | word map applied after the model (is to was, are to were, ...) |
| `protected_patterns`, `validation` | what must not change, and the limits that raise a flag |
| `preserve_case`, `check_removals` | the capitalisation and removal guards |

## Safety

- Runs locally; no project text is sent anywhere.
- A person approves every change; nothing is written without approval.
- Dry-run mode, edit protection (notes changed since extraction are skipped), and a flag on every doubtful suggestion.
- The write-back reports a per-note result and continues if one note fails (for example, owned by another user in a workshared model).
- If the Excel file is open, rows wait in `pending_report_rows.json` and are added on the next run.

## Limitations

- Setting a note's text removes formatting inside that note (bold, underline, bullets). Test on a formatted note first.
- The selection trigger list is a heuristic. A verb that is not on it is skipped, so check the *Skipped* filter on a first run.
- Output quality depends on the local model. The guards make bad answers harmless, but cannot make a weak model good.
- Dynamo stays busy while the review page is open.
- A replaced report row keeps only the latest change for that element.

## Tests

```bash
python -m unittest discover -s tests -v
```

51 tests run without Revit or Ollama: selection and validation rules, the guards, the full pipeline against a fake Ollama server, the review export, the Excel report (create, replace by Element ID, locked file, a file re-saved by Excel), and `node3_write_back.py` against a fake Revit document. One test is skipped automatically if `openpyxl` is not installed.

## Repository layout

```
tool/       ollama_client.py, review_ui.py, report_xlsx.py, rules.json   (keep together)
dynamo/     one script per Dynamo Python node + wiring guide
samples/    sample_notes.json, sample_report.xlsx
tests/      unit and integration tests with simulated Revit and Ollama
docs/       write-ups and screenshots (docs/images)
```

## Possible next steps

Preserve in-note formatting with Revit's formatted-text API, rule packs for other standards and languages, feed the Excel log into a QA dashboard, and package the nodes as a Dynamo package.

## License

MIT. See [LICENSE](LICENSE).
