import clr
import re

clr.AddReference("RevitServices")
import RevitServices
from RevitServices.Transactions import TransactionManager

# Safely unpack inputs
text_inputs = IN[0] if isinstance(IN[0], list) else [IN[0]]
old_inputs   = IN[1] if isinstance(IN[1], list) else [IN[1]]
new_inputs   = IN[2] if isinstance(IN[2], list) else [IN[2]]

# Unwrap elements
revit_notes = (
    UnwrapElement(IN[3])
    if isinstance(IN[3], list)
    else [UnwrapElement(IN[3])]
)

# Clean find/replace lists
old_words = [str(x) if x is not None else "" for x in old_inputs]
new_words = [str(y) if y is not None else "" for y in new_inputs]

doc = RevitServices.Persistence.DocumentManager.Instance.CurrentDBDocument

TransactionManager.Instance.EnsureInTransaction(doc)

output_strings = []

# Loop through every element and corresponding text
for note_element, original_text in zip(revit_notes, text_inputs):

    if note_element is None or original_text is None:
        output_strings.append("")
        continue

    current_text = str(original_text)
    has_changed = False

    # Run through find/replace pairs sequentially
    for old, new in zip(old_words, new_words):

        # Skip empty find values
        if old.strip() == "":
            continue

        # -------------------------------------------------
        # WHOLE WORD REPLACEMENT
        #
        # \b prevents replacing part of another word.
        #
        # Example:
        # "is" -> "was"
        #
        # "is"       becomes "was"
        # "This is"  becomes "This was"
        # "wish"     stays "wish"
        # "isometric" stays "isometric"
        # -------------------------------------------------

        pattern = r"\b" + re.escape(old) + r"\b"

        # Case-sensitive replacement
        new_text, count = re.subn(
            pattern,
            new,
            current_text
        )

        if count > 0:
            current_text = new_text
            has_changed = True

        # -------------------------------------------------
        # Handle uppercase version
        # -------------------------------------------------

        old_upper = old.upper()
        new_upper = new.upper()

        if old_upper != old:
            pattern_upper = r"\b" + re.escape(old_upper) + r"\b"

            new_text, count = re.subn(
                pattern_upper,
                new_upper,
                current_text
            )

            if count > 0:
                current_text = new_text
                has_changed = True

        # -------------------------------------------------
        # Handle Capitalized version
        # -------------------------------------------------

        old_cap = old.capitalize()
        new_cap = new.capitalize()

        if old_cap != old and old_cap != old_upper:
            pattern_cap = r"\b" + re.escape(old_cap) + r"\b"

            new_text, count = re.subn(
                pattern_cap,
                new_cap,
                current_text
            )

            if count > 0:
                current_text = new_text
                has_changed = True

    # Push changed text back into Revit
    if has_changed:
        try:
            note_element.Text = current_text
        except:
            pass

    output_strings.append(current_text)

TransactionManager.Instance.TransactionTaskDone()

OUT = output_strings