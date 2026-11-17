# Dynamo Python Script node (engine: CPython3, Revit 2025). Paste this whole file into the node.
# The other files in tool/ must sit in the folder you connect to the node (see ../README.md).

# ======================================================================
# NODE 2: review UI   (1 input) - blocks until you click "Save & finish" or "Cancel"
# IN[0] results path (from node 1)
# OUT = path to approved.json
# ======================================================================
import sys, os, importlib.util

folder = os.path.dirname(IN[0])
if folder not in sys.path:
    sys.path.insert(0, folder)

for name in ("ollama_client", "review_ui"):   # fresh load of both modules
    p = os.path.join(folder, name + ".py")
    if not os.path.isfile(p):
        raise Exception(name + ".py not found at: " + p)
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)

OUT = sys.modules["review_ui"].run(IN[0], timeout_min=30)   # gives up after 30 min; add port=8766 if 8765 is busy
