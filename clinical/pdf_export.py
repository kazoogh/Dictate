"""Export clinical answer sheets to PDF (stdlib only — no reportlab)."""

from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path


def format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def build_pdf_filename(session: dict) -> str:
    dt = datetime.fromisoformat(session["started_at"])
    date_str = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%H%M")
    procedure = session["procedure_type"].replace(" ", "_")
    return f"{date_str}_{procedure}_{time_str}_answer_sheet.pdf"


def _pdf_escape(text: str) -> str:
    safe = text.encode("latin-1", "replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _PdfBuilder:
    WIDTH = 612
    HEIGHT = 792
    LEFT = 54
    BOTTOM = 54
    TOP = 738
    WRAP = 88

    def __init__(self):
        self._pages: list[list[str]] = [[]]
        self._y = self.TOP

    def _new_page(self):
        self._pages.append([])
        self._y = self.TOP

    def line(self, text: str, size: int = 10, bold: bool = False, gap: int | None = None):
        font = "F2" if bold else "F1"
        step = gap if gap is not None else size + 4
        for part in textwrap.wrap(text, width=self.WRAP) or [""]:
            if self._y < self.BOTTOM:
                self._new_page()
            escaped = _pdf_escape(part)
            self._pages[-1].append(
                f"BT /{font} {size} Tf {self.LEFT} {self._y} Td ({escaped}) Tj ET"
            )
            self._y -= step

    def blank(self, px: int = 8):
        self._y -= px
        if self._y < self.BOTTOM:
            self._new_page()

    def build_bytes(self) -> bytes:
        objects: list[bytes] = []
        page_obj_nums: list[int] = []

        def add_obj(data: str | bytes) -> int:
            if isinstance(data, str):
                data = data.encode("latin-1")
            objects.append(data)
            return len(objects)

        add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        f1 = len(objects)
        add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        f2 = len(objects)

        content_obj_nums: list[int] = []
        for page_ops in self._pages:
            stream = "\n".join(page_ops).encode("latin-1")
            content = f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream"
            content_obj_nums.append(add_obj(content))

        pages_kids = []
        for content_num in content_obj_nums:
            page = (
                f"<< /Type /Page /Parent {{PAGES}} 0 R "
                f"/MediaBox [0 0 {self.WIDTH} {self.HEIGHT}] "
                f"/Contents {content_num} 0 R "
                f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> >>"
            )
            page_obj_nums.append(add_obj(page))
            pages_kids.append(f"{page_obj_nums[-1]} 0 R")

        pages_obj = add_obj(
            f"<< /Type /Pages /Kids [{' '.join(pages_kids)}] /Count {len(pages_kids)} >>"
        )
        for i, page_num in enumerate(page_obj_nums):
            objects[page_num - 1] = objects[page_num - 1].decode("latin-1").replace("{PAGES}", str(pages_obj)).encode("latin-1")

        catalog = add_obj(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>")

        out = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for i, obj in enumerate(objects, start=1):
            offsets.append(len(out))
            out.extend(f"{i} 0 obj\n".encode("latin-1"))
            out.extend(obj)
            out.extend(b"\nendobj\n")

        xref_pos = len(out)
        out.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        out.extend(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
        out.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
        )
        return bytes(out)


def export_answer_sheet_pdf(session: dict, sheet: dict, pdf_path: Path) -> Path:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = _PdfBuilder()

    pdf.line("Clinical Note Answer Sheet", 18, bold=True, gap=22)
    pdf.line("Review aid only - not a finalized clinical note", 9, gap=18)

    header = sheet.get("header", {})
    pdf.line(f"Procedure Type: {header.get('procedure_type', '')}")
    rec = header.get("recording_date_time", "")
    try:
        rec_display = datetime.fromisoformat(rec).strftime("%b %d, %Y %I:%M %p")
    except ValueError:
        rec_display = rec
    pdf.line(f"Recording: {rec_display}")
    pdf.line(f"Duration: {format_duration(int(header.get('duration_seconds', 0)))}")
    pdf.line(f"Status: {sheet.get('final_note_status', '')}", gap=16)

    pdf.line("Detected Details", 13, bold=True, gap=14)
    d = sheet.get("detected_details", {})
    for label, key, ev_key in (
        ("Provider", "provider", "provider_evidence"),
        ("Assistant", "assistant", "assistant_evidence"),
        ("Operatory", "operatory", "operatory_evidence"),
        ("Tooth/Teeth", "tooth_number", "tooth_evidence"),
    ):
        pdf.line(f"{label}: {d.get(key, '')} - {d.get(ev_key, '') or 'N/A'}", 9, gap=12)
    pdf.blank(6)

    pdf.line("Template Answers", 13, bold=True, gap=14)
    for field in sheet.get("template_answers", []):
        pdf.line(field.get("label", ""), 10, bold=True, gap=12)
        pdf.line(f"  Answer: {field.get('suggested_answer', '')}", 9, gap=11)
        pdf.line(f"  Evidence: {field.get('evidence', '')}", 9, gap=11)
        pdf.line(f"  Confidence: {field.get('confidence', '')}", 9, gap=14)

    if sheet.get("missing_unclear_fields"):
        pdf.line("Missing / Unclear Fields", 13, bold=True, gap=12)
        for item in sheet["missing_unclear_fields"]:
            pdf.line(f"- {item}", 9, gap=11)

    if sheet.get("patient_questions_concerns"):
        pdf.line("Patient Questions / Concerns", 13, bold=True, gap=12)
        for item in sheet["patient_questions_concerns"]:
            pdf.line(f"- {item}", 9, gap=11)

    if sheet.get("warnings"):
        pdf.line("Warnings", 13, bold=True, gap=12)
        for w in sheet["warnings"]:
            pdf.line(f"- [{w.get('type', '')}] {w.get('message', '')}", 9, gap=11)

    pdf.line(f"Final Note Status: {sheet.get('final_note_status', '')}", 11, bold=True)

    pdf_path.write_bytes(pdf.build_bytes())
    return pdf_path
