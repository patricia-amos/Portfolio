import copy
import unittest

import helpers  # noqa: F401  (sets up the import path)
import ollama_client as oc

CFG = oc.load_rules()


def note(text, sheet="A101"):
    return {"unique_id": "x", "sheet_number": sheet, "text": text}


class SelectionTests(unittest.TestCase):
    def test_action_note_is_selected(self):
        self.assertIsNone(oc.skip_reason(note("Install anchors as required."), CFG))

    def test_reference_only_note_is_skipped(self):
        self.assertIn("reference_only", oc.skip_reason(note("See detail 3/A501 for connection."), CFG))

    def test_short_caps_title_is_skipped(self):
        self.assertIn("short_caps_title_or_tag", oc.skip_reason(note("LEVEL 1 FLOOR PLAN"), CFG))

    def test_removal_phrase_is_always_selected_even_when_one_word(self):
        self.assertIsNone(oc.skip_reason(note("TBC"), CFG))

    def test_be_have_do_forms_trigger_selection(self):
        self.assertIsNone(oc.skip_reason(note("Walls are fire-rated"), CFG))

    def test_note_without_trigger_is_skipped(self):
        self.assertIn("require_any", oc.skip_reason(note("Existing wall to remain here"), CFG))

    def test_sheet_exclude(self):
        cfg = copy.deepcopy(CFG)
        cfg["selection"]["sheet_exclude"] = ["^G"]
        self.assertEqual(oc.skip_reason(note("Install anchors.", sheet="G000"), cfg), "sheet in sheet_exclude")

    def test_selection_can_be_switched_off(self):
        cfg = copy.deepcopy(CFG)
        cfg["selection"]["enabled"] = False
        self.assertIsNone(oc.skip_reason(note("LEVEL 1 FLOOR PLAN"), cfg))


class ValidationTests(unittest.TestCase):
    def test_clean_change_has_no_flags(self):
        self.assertEqual(oc.validate("Install anchors as required.", "Installed anchors.", CFG), [])

    def test_tense_change_of_to_be_is_not_flagged(self):
        self.assertEqual(oc.validate("Existing partition is to be removed.", "Existing partition was removed.", CFG), [])

    def test_changed_number_is_flagged(self):
        flags = oc.validate("Provide 2 hr rated assembly.", "Provided 3 hr rated assembly.", CFG)
        self.assertTrue(any("Protected text changed" in f for f in flags))

    def test_removing_tbc_is_allowed(self):
        flags = oc.validate("Door type TBC on site.", "Door type.", CFG)
        self.assertFalse(any("Protected text changed" in f for f in flags))

    def test_whole_note_removal_is_flagged_for_review(self):
        self.assertTrue(any("Whole note removed" in f for f in oc.validate("Door type TBC on site.", "", CFG)))

    def test_deleting_real_content_is_flagged(self):
        flags = oc.validate("Countertop w Backsplash \u2013 Provide Blocking in Walls as Required", "Provided Blocking in Walls", CFG)
        self.assertTrue(any("not a removal phrase" in f for f in flags))

    def test_line_break_change_is_flagged(self):
        self.assertTrue(any("Line break" in f for f in oc.validate("One\nTwo", "One Two", CFG)))


if __name__ == "__main__":
    unittest.main()
