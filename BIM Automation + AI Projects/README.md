# Revit Documentation Automation: From Rule-Based to AI-Assisted

Three Dynamo workflows for cleaning up sheet documentation in Revit. Two are rule-based automation; the third adds AI, using a local language model (Ollama) to rewrite text notes.

## 1. PopulateMultipleSheetParameters

Automates populating parameters across multiple sheets in one run, so sheet information does not have to be filled in by hand sheet by sheet.

## 2. ReplaceTextNotesBasedOnExcelDictionary

Automates batch replacement of wording in text notes using an Excel dictionary.

- Filters sheets by a grouping parameter.
- Replaces text notes on those sheets and on the views placed on them.
- Reads `Dictionary.xlsx`: column 1 holds the words to find, column 2 the replacement words.

## 3. AI-Assisted Text Note Markup

An automation upgrade on script 2. Instead of a fixed dictionary, a local language model rewrites text notes according to a set of rules. It is intended for turning IFC-derived models into as-built documentation (past tense, removal of "as required" and pending-input phrases).

1. Dynamo extracts text notes from the selected sheets.
2. A Python script sends them to a local Ollama model, applying a rules template.
3. The proposed changes are reviewed, approved or edited.
4. Dynamo writes the new text back to the model using `TextNote.SetText`.
5. An Excel report is appended to, listing only the notes that actually changed: sheet number, Element ID, Original Text, New Text and Date of update.

**Status:** Extraction and write-back are built. The Python/Ollama script, rules template and review step are still in progress.

## Tools Used

- **Autodesk Revit 2025**: host application (Revit's sample architectural model is used for demonstration)
- **Dynamo 3.3.0**: visual programming and automation of Revit tasks
- **Clockwork package**: additional Dynamo nodes used in the dictionary replace graph
- **Python**: scripting inside Dynamo, used to call the language model
- **Ollama 0.40.2**: runs the language model locally
- **Microsoft Excel**: holds the replacement dictionary and the change report
