"""End-to-end check of ollama_client.run() against a fake Ollama HTTP server (no real model needed)."""
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import helpers  # noqa: F401
import ollama_client as oc

ANSWERS = {"Install anchors as required.": "Installed anchors.", "Walls are 2 hr rated.": "Walls were 2 hr rated."}


class FakeOllama(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *a):
        pass

    def _send(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send({"models": [{"name": "llama3.1:8b"}]})

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.requests.append(data)
        text = data["messages"][-1]["content"]
        self._send({"message": {"content": json.dumps({"new_text": ANSWERS.get(text, text)})}})


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.tmp = tempfile.mkdtemp()
        cfg = oc.load_rules()
        cfg["ollama_url"] = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.rules = os.path.join(cls.tmp, "rules.json")
        with open(cls.rules, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_notes(self, notes, **kw):
        return oc.run(notes, rules_path=self.rules, out_path=os.path.join(self.tmp, "results.json"), progress=None, **kw)

    def test_statuses_and_counts(self):
        notes = [
            {"unique_id": "1", "element_id": 1, "sheet_number": "A402", "text": "Install anchors as required."},
            {"unique_id": "2", "element_id": 2, "sheet_number": "A501", "text": "See detail 3/A501 for connection."},
            {"unique_id": "3", "element_id": 3, "sheet_number": "A101", "text": "Walls are 2 hr rated."},
        ]
        doc = self.run_notes(notes, report_folder=os.path.join(self.tmp, "reports"))
        by_id = {i["unique_id"]: i for i in doc["items"]}
        self.assertEqual(by_id["1"]["new_text"], "Installed anchors.")
        self.assertEqual(by_id["1"]["status"], "pending")
        self.assertEqual(by_id["2"]["status"], "skipped")
        self.assertEqual(by_id["3"]["new_text"], "Walls were 2 hr rated.")
        self.assertEqual((doc["meta"]["selected"], doc["meta"]["skipped"]), (2, 1))
        self.assertTrue(doc["meta"]["report_folder"].endswith("reports"))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "reports")))   # created up front
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "results.json")))

    def test_examples_are_sent_as_chat_turns_and_runs_are_repeatable(self):
        FakeOllama.requests.clear()
        self.run_notes([{"unique_id": "1", "element_id": 1, "sheet_number": "A1", "text": "Install anchors as required."}])
        req = FakeOllama.requests[-1]
        roles = [m["role"] for m in req["messages"]]
        self.assertEqual(roles[0], "system")
        self.assertEqual(roles[-1], "user")
        self.assertIn("assistant", roles)                      # worked examples are earlier turns
        self.assertEqual(req["options"]["temperature"], 0)
        self.assertEqual(req["format"], "json")

    def test_identical_lines_are_sent_once(self):
        FakeOllama.requests.clear()
        notes = [{"unique_id": str(i), "element_id": i, "sheet_number": "A1", "text": "Install anchors as required."} for i in range(3)]
        self.run_notes(notes)
        self.assertEqual(len(FakeOllama.requests), 1)

    def test_unusable_report_folder_fails_before_any_model_call(self):
        blocker = os.path.join(self.tmp, "afile")
        open(blocker, "w").close()
        FakeOllama.requests.clear()
        with self.assertRaises(Exception) as ctx:
            self.run_notes([{"unique_id": "1", "element_id": 1, "sheet_number": "A1", "text": "Install anchors."}],
                           report_folder=os.path.join(blocker, "sub"))
        self.assertIn("Report output folder", str(ctx.exception))
        self.assertEqual(FakeOllama.requests, [])

    def test_missing_model_gives_a_helpful_error(self):
        cfg = oc.load_rules(self.rules)
        cfg["model"] = "not-installed:1b"
        with self.assertRaises(RuntimeError) as ctx:
            oc.check_ollama(cfg)
        self.assertIn("ollama pull", str(ctx.exception))

    def test_unreachable_ollama_gives_a_helpful_error(self):
        cfg = oc.load_rules(self.rules)
        cfg["ollama_url"] = "http://127.0.0.1:9"
        with self.assertRaises(RuntimeError) as ctx:
            oc.check_ollama(cfg)
        self.assertIn("ollama serve", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
