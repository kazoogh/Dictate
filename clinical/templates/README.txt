Clinical note templates for Dictate (JSON format)

DO NOT upload DOCX or PDF — the app cannot read those reliably.

HOW TO ADD / UPDATE TEMPLATES
-----------------------------
1. Best: Edit or add .json files in this folder:
   C:\Users\INTERN4\Dictate\clinical\templates\

2. Copy an existing file (e.g. crown.json) and change fields to match
   your Dentrix Ascend clinical note questions.

3. Restart Dictate after adding a new template file.

FIELD TYPES (map from Dentrix)
------------------------------
  yes_no           → Yes/No or single-choice pick list
  multiple_choice  → Pick one from allowed_answers list
  short_answer     → Short text (tooth #, material, etc.)
  free_text        → Narrative / comments

Each field needs:
  id, label, type, required, evidence_required, fallback ("Needs Human Review")
  For yes_no / multiple_choice: allowed_answers array

PROCEDURE TYPE NAMES (must match filename mapping in clinical/paths.py)
-----------------------------------------------------------------------
  Extraction, Filling, Crown, Denture, New Patient Exam, Other

If you have Dentrix templates in Word/PDF, type the questions into JSON
using crown.json as a guide, or send a structured spreadsheet (one row
per question) for conversion — do not paste unstructured paragraphs.
