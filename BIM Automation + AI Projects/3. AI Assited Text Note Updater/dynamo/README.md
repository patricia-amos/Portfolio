# Dynamo graph

Each file in this folder is pasted whole into its own **Python Script** node. Set every node's engine to **CPython3** and Dynamo's run mode to **Manual**.

The scripts in `../tool/` (`ollama_client.py`, `review_ui.py`, `report_xlsx.py`, `rules.json`) must sit together in one folder. That folder is the one you give Node 1.

## Wiring

```
[your extraction nodes] --> unique IDs, element IDs, sheet numbers, texts --+
[String: path to the tool folder] -----------------------------------------+
[Code Block: "C:/BIM/Reports";] -------------------------------------------+
                                                                            v
                                 NODE 1  node1_ask_ollama.py   (6 inputs)  -> results.json path
                                                                            v
                                 NODE 2  node2_review.py       (1 input)   -> approved.json path
                                                                            v
[Boolean: False = dry run, True = apply] ---> NODE 3  node3_write_back.py  -> Watch node
```

| Node | Port | Connect to |
|---|---|---|
| 1 | `IN[0]` | String: the folder that holds the `tool/` files |
| 1 | `IN[1]` | Unique IDs of the text notes |
| 1 | `IN[2]` | Element IDs |
| 1 | `IN[3]` | Sheet numbers |
| 1 | `IN[4]` | Text of each note |
| 1 | `IN[5]` | Code Block with the report folder (forward slashes, or doubled backslashes) |
| 2 | `IN[0]` | Output of node 1 |
| 3 | `IN[0]` | **Output of node 2** (the `approved.json` path) |
| 3 | `IN[1]` | Boolean: False = dry run, True = apply |
| 3 | `IN[2]` | *(optional)* a different report folder than the one given to node 1 |

The four input lists of node 1 must be flat, the same length and in the same order, one entry per text note.

## Running it

1. Make sure Ollama is running and the model named in `rules.json` is pulled.
2. With the Boolean on **False**, press Run. Node 1 sends the notes to the model, then the review page opens. Approve, reject or edit, then click **Save & finish** (or **Cancel** to apply nothing).
3. Read the Watch node: it shows what node 3 would change and where the report will be saved.
4. Set the Boolean to **True** and run again. Node 3 changes the model and updates `Text_notes_update_report.xlsx`.

Do not connect your own `TextNote.SetText` nodes as well as node 3; both would edit the same notes.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `ollama_client.py not found at: ...` | wrong folder in node 1 `IN[0]` |
| `Ollama not reachable` / `Model ... not installed` | start Ollama, or `ollama pull <model>` |
| Browser does not open | go to `http://127.0.0.1:8765` while node 2 is running |
| `NODE 3 ERROR ... IN[0] must be the approved.json path` | node 3 `IN[0]` is not wired to node 2's output |
| Report not created | Boolean is still False, or nothing was changed; read the second line of the Watch output |
| `REPORT FAILED ... close it in Excel` | the changes were applied; the rows are kept and added on the next run |
