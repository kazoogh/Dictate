"""OpenAI answer sheet generation (clinical sessions only)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

SYSTEM_PROMPT = """You are generating a clinical note answer sheet for a dental practice. Use only the transcript and the selected clinical note template. Do not invent, assume, or infer clinical facts that are not clearly supported by the transcript. If a field is not clearly answered, write 'Needs Human Review.' For every answer, provide brief evidence from the transcript. Do not finalize the chart note. This output is only a staff review aid.

Return valid JSON matching this structure:
{
  "header": {
    "procedure_type": string,
    "recording_date_time": string,
    "duration_seconds": number,
    "status": "Needs Review" | "Ready for Dentrix"
  },
  "detected_details": {
    "provider": string,
    "provider_evidence": string,
    "assistant": string,
    "assistant_evidence": string,
    "operatory": string,
    "operatory_evidence": string,
    "tooth_number": string,
    "tooth_evidence": string
  },
  "template_answers": [
    {
      "field_id": string,
      "label": string,
      "suggested_answer": string,
      "evidence": string,
      "confidence": "High" | "Medium" | "Low" | "Needs Human Review"
    }
  ],
  "missing_unclear_fields": string[],
  "patient_questions_concerns": string[],
  "warnings": [
    { "type": string, "message": string }
  ],
  "final_note_status": "Needs Review" | "Ready for Dentrix"
}

Rules:
- Output fields in the same order as the template.
- For fields with allowed_answers (multiple_choice or yes_no), suggested_answer MUST exactly match one of the allowed options, or be "Needs Human Review".
- For teeth_restored, list tooth numbers and surfaces exactly as stated (e.g. "14 MOD").
- Quadrant selections: use UR, UL, LR, LL when stated.
- final_note_status must be "Needs Review" if any required template field has suggested_answer of "Needs Human Review".
- Include warnings for possible missing consent, tooth number, anesthesia, post-op instructions, or unclear next visit when applicable.
- Return ONLY valid JSON, no markdown fences."""


def generate_answer_sheet(
    api_key: str,
    model: str,
    transcript: str,
    template: dict,
    procedure_type: str,
    recording_datetime: str,
    duration_seconds: int,
) -> dict:
    template_json = json.dumps(template, indent=2)
    user_prompt = f"""Procedure Type: {procedure_type}
Recording Date/Time: {recording_datetime}
Duration (seconds): {duration_seconds}

Clinical Note Template:
{template_json}

Transcript:
{transcript}

Generate the answer sheet JSON now."""

    content = _call_openai(api_key, model, user_prompt)
    sheet = _parse_answer_sheet(
        content, procedure_type, recording_datetime, duration_seconds, template
    )
    return _validate_and_adjust_status(sheet, template)


def _call_openai(api_key: str, model: str, user_prompt: str) -> str:
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {exc.code}: {detail[:200]}") from exc
    return body["choices"][0]["message"]["content"]


def _parse_answer_sheet(
    content: str,
    procedure_type: str,
    recording_datetime: str,
    duration_seconds: int,
    template: dict,
) -> dict:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            raise ValueError("LLM did not return valid JSON") from None
        parsed = json.loads(match.group(0))

    parsed["header"] = {
        "procedure_type": procedure_type,
        "recording_date_time": recording_datetime,
        "duration_seconds": duration_seconds,
        "status": "Ready for Dentrix"
        if parsed.get("final_note_status") == "Ready for Dentrix"
        else "Needs Review",
    }

    answer_map = {a["field_id"]: a for a in parsed.get("template_answers", [])}
    parsed["template_answers"] = []
    for field in template.get("fields", []):
        existing = answer_map.get(field["id"])
        if existing:
            existing = _normalize_field_answer(existing, field)
            parsed["template_answers"].append(existing)
        else:
            parsed["template_answers"].append(
                {
                    "field_id": field["id"],
                    "label": field["label"],
                    "suggested_answer": field.get("fallback", "Needs Human Review"),
                    "evidence": "Not found in transcript",
                    "confidence": "Needs Human Review",
                }
            )

    parsed.setdefault(
        "detected_details",
        {
            "provider": "Needs Human Review",
            "provider_evidence": "",
            "assistant": "Needs Human Review",
            "assistant_evidence": "",
            "operatory": "Needs Human Review",
            "operatory_evidence": "",
            "tooth_number": "Needs Human Review",
            "tooth_evidence": "",
        },
    )
    parsed.setdefault("missing_unclear_fields", [])
    parsed.setdefault("patient_questions_concerns", [])
    parsed.setdefault("warnings", [])
    return parsed


def _normalize_field_answer(answer: dict, field: dict) -> dict:
    """Snap multiple-choice answers to allowed options; reject guesses."""
    allowed = field.get("allowed_answers")
    if not allowed:
        return answer
    suggested = (answer.get("suggested_answer") or "").strip()
    if suggested in allowed:
        return answer
    # Case-insensitive fuzzy match for long anesthetic strings
    lower_map = {a.lower(): a for a in allowed}
    if suggested.lower() in lower_map:
        answer = {**answer, "suggested_answer": lower_map[suggested.lower()]}
        return answer
    answer["suggested_answer"] = field.get("fallback", "Needs Human Review")
    answer["confidence"] = "Needs Human Review"
    if not answer.get("evidence"):
        answer["evidence"] = "Answer not in allowed quick-pick list"
    return answer


def _validate_and_adjust_status(sheet: dict, template: dict) -> dict:
    required = [f for f in template.get("fields", []) if f.get("required")]
    has_missing = any(
        not (ans := next((a for a in sheet["template_answers"] if a["field_id"] == f["id"]), None))
        or ans["suggested_answer"] == "Needs Human Review"
        or ans.get("confidence") == "Needs Human Review"
        for f in required
    )
    if has_missing:
        sheet["final_note_status"] = "Needs Review"
        sheet["header"]["status"] = "Needs Review"
    return sheet
