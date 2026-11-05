# Dynamo Python Script node (engine: CPython3, Revit 2025). Paste this whole file into the node.
# The other files in tool/ must sit in the folder you connect to the node (see ../README.md).

# ======================================================================
# NODE 1: ask Ollama   (6 inputs)
# IN[0] scripts folder | IN[1] unique ids | IN[2] element ids | IN[3] sheet numbers | IN[4] texts
# IN[5] report output folder (a Code Block / String, e.g. "C:/BIM/Reports"; empty = scripts folder)
#       it is only remembered here; the Excel report itself is written by Node 3, after the model was changed
# OUT = path to results.json
# ======================================================================
import sys, os, importlib.util

folder = IN[0]
path = os.path.join(folder, "ollama_client.py")
if not os.path.isfile(path):
    raise Exception("ollama_client.py not found at: " + path)
if folder not in sys.path:
    sys.path.insert(0, folder)

spec = importlib.util.spec_from_file_location("ollama_client", path)
ollama_client = importlib.util.module_from_spec(spec)
sys.modules["ollama_client"] = ollama_client      # lets review_ui import it later
spec.loader.exec_module(ollama_client)            # fresh load on every run

notes = [{"unique_id": u, "element_id": e, "sheet_number": s, "text": t}
         for u, e, s, t in zip(IN[1], IN[2], IN[3], IN[4])]
results_path = os.path.join(folder, "results.json")
ollama_client.run(notes, out_path=results_path, report_folder=IN[5] if len(IN) > 5 else None)
OUT = results_path
