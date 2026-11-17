import copy
import unittest
from unittest import mock

import helpers  # noqa: F401
import ollama_client as oc

CFG = oc.load_rules()
SYSTEM = oc.build_system_prompt(CFG)


def rewrite_with(answers, text, sheet="G000"):
    """Run rewrite_note with a fake model that answers from a dict (anything else comes back unchanged)."""
    with mock.patch.object(oc, "rewrite", lambda cfg, system, t: answers.get(t, t)):
        return oc.rewrite_note(CFG, SYSTEM, {"unique_id": "x", "sheet_number": sheet, "text": text}, {})


class GuardTests(unittest.TestCase):
    def test_title_case_is_restored(self):
        self.assertEqual(oc.restore_case("Provide Blocking in Walls", "Provided blocking in walls"), "Provided Blocking in Walls")

    def test_deleted_words_and_punctuation_are_put_back(self):
        old = "Ensure that Positioning is set to: Auto \u2013 Internal Origin and then click Open. (Figure 2)"
        new = "Positioning is set to Auto \u2013 Internal Origin and then click Open."
        fixed = oc.guard_removals(old, new, CFG)
        for piece in ("Ensure that", "set to:", "(Figure 2)"):
            self.assertIn(piece, fixed)

    def test_removal_phrase_may_disappear(self):
        self.assertEqual(oc.guard_removals("Install anchors as required.", "Installed anchors.", CFG), "Installed anchors.")

    def test_is_to_be_becomes_was(self):
        self.assertEqual(oc.guard_removals("Existing partition is to be removed.", "Existing partition was removed.", CFG),
                         "Existing partition was removed.")

    def test_unrelated_answer_is_detected(self):
        self.assertTrue(oc.looks_unrelated("This is the: Snowdon Towers Sample Architectural.rvt model",
                                           "Countertop w Backsplash - Provided Blocking in Walls"))
        self.assertFalse(oc.looks_unrelated("Install anchors as required.", "Installed anchors."))

    def test_forced_replacements(self):
        self.assertEqual(oc.enforce("Walls are rated. Is it fire-rated? The door is open.", CFG),
                         "Walls were rated. Was it fire-rated? The door was open.")

    def test_forced_replacements_can_be_disabled(self):
        cfg = copy.deepcopy(CFG)
        cfg["forced_replacements"]["enabled"] = False
        self.assertEqual(oc.enforce("Walls are rated.", cfg), "Walls are rated.")


class RewriteNoteTests(unittest.TestCase):
    def test_model_that_copies_an_example_is_rejected_and_tense_still_fixed(self):
        text = "This is the: Snowdon Towers Sample Architectural.rvt model"
        new, flags = rewrite_with({text: "Countertop w Backsplash - Provided Blocking in Walls"}, text)
        self.assertEqual(new, "This was the: Snowdon Towers Sample Architectural.rvt model")
        self.assertTrue(any("unrelated" in f for f in flags))

    def test_over_deleting_model_is_repaired(self):
        text = "Countertop w Backsplash \u2013 Provide Blocking in Walls as Required"
        new, _ = rewrite_with({text: "Provided blocking in walls"}, text)
        self.assertEqual(new, "Countertop w Backsplash \u2013 Provided Blocking in Walls")

    def test_line_breaks_and_trailing_separator_are_kept(self):
        text = "Install anchors as required.\r\rSee detail 3/A501\rWalls are rated.\r"
        new, flags = rewrite_with({"Install anchors as required.": "Installed anchors.", "Walls are rated.": "Walls were rated."}, text)
        self.assertEqual(new, "Installed anchors.\r\rSee detail 3/A501\rWalls were rated.\r")
        self.assertEqual(flags, [])

    def test_line_that_is_only_a_removal_phrase_is_dropped_with_its_line_break(self):
        text = "Install anchors.\rDoor type TBC on site.\rPaint walls."
        new, _ = rewrite_with({"Install anchors.": "Installed anchors.", "Door type TBC on site.": "", "Paint walls.": "Painted walls."}, text)
        self.assertEqual(new, "Installed anchors.\rPainted walls.")

    def test_note_that_is_entirely_a_removal_phrase_becomes_empty(self):
        text = "Contractor to verify dimensions on site."
        new, _ = rewrite_with({text: ""}, text)
        self.assertEqual(new, "")

    def test_model_failure_keeps_the_original_and_flags_it(self):
        def boom(cfg, system, text):
            raise RuntimeError("model unavailable")
        with mock.patch.object(oc, "rewrite", boom):
            new, flags = oc.rewrite_note(CFG, SYSTEM, {"unique_id": "x", "sheet_number": "A1", "text": "Install anchors."}, {})
        self.assertEqual(new, "Install anchors.")
        self.assertTrue(any("Ollama error" in f for f in flags))


if __name__ == "__main__":
    unittest.main()
