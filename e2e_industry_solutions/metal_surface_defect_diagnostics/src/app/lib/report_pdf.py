"""Downloadable PDF of one diagnosis (fpdf2, pure Python, core fonts).

Layout: title bar, review banner (when human review is required), image + classification
summary, the diagnostic report (or the reviewed playbook entry), source line and disclaimer.
Core PDF fonts are Latin-1 only, so text is transliterated first.
"""

from __future__ import annotations

import io
import re

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image

_TRANSLIT = {
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"',
    "\u201d": '"', "\u2022": "-", "\u2026": "...", "\u2265": ">=", "\u2264": "<=", "\u00a0": " ",
    "\u2192": "->", "\u00d7": "x",
}
SEVERITY_RGB = {
    "Critical": (183, 28, 28), "High": (211, 47, 47), "Medium": (239, 108, 0), "Low": (46, 125, 50),
}
GREY = (97, 97, 97)


def latin1(text) -> str:
    s = str(text if text is not None else "")
    for k, v in _TRANSLIT.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _inline(text: str) -> str:
    """Keep **bold** (fpdf2 markdown), neutralise other markers fpdf2 would interpret."""
    text = latin1(text).replace("__", "_ _").replace("--", "- -").replace("~~", "~ ~")
    return re.sub(r"(?<!\*)\*(?!\*)([^*]+)(?<!\*)\*(?!\*)", r"\1", text)  # drop *italics*


class _Pdf(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*GREY)
        self.cell(0, 5, f"Metal Surface Defect Diagnostics - POC - page {self.page_no()}/{{nb}}", align="C")


def _markdown_block(pdf: FPDF, markdown: str) -> None:
    width = pdf.epw
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            pdf.ln(1.5)
            continue
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.*)$", line)
        bullet = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        numbered = re.match(r"^(\s*)(\d+)[.)]\s+(.*)$", line)
        pdf.set_x(pdf.l_margin)
        if heading:
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(21, 101, 192)
            pdf.multi_cell(width, 5.5, latin1(heading.group(1).strip("* ")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)
        elif bullet or numbered:
            indent = len((bullet or numbered).group(1)) // 2
            marker = "-" if bullet else f"{numbered.group(2)}."
            body = bullet.group(2) if bullet else numbered.group(3)
            x = pdf.l_margin + 3 + 4 * indent
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_x(x)
            pdf.cell(4, 4.8, marker)
            pdf.multi_cell(width - (x - pdf.l_margin) - 4, 4.8, _inline(body), markdown=True,
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.set_font("Helvetica", "", 9.5)
            pdf.multi_cell(width, 4.8, _inline(line), markdown=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def build_pdf(
    *,
    generated_at: str,
    file_name: str,
    image_bytes: bytes,
    summary: list[tuple[str, str]],
    severity: str,
    human_review: bool,
    review_reasons: tuple[str, ...] | list[str],
    body_title: str,
    body_markdown: str,
    source_line: str | None,
    disclaimer: str,
) -> bytes:
    """Return the PDF as bytes."""
    pdf = _Pdf(format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.alias_nb_pages()
    pdf.add_page()

    # Title bar
    pdf.set_fill_color(21, 101, 192)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 11, "  Metal Surface Defect Diagnostic Report", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*GREY)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 6, latin1(f"Generated {generated_at} - image: {file_name}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    # Review banner
    if human_review:
        pdf.set_fill_color(255, 243, 224)
        pdf.set_text_color(230, 81, 0)
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(0, 6, latin1("UNCONFIRMED - expert review required. " + " ".join(review_reasons)),
                       fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    # Image + summary table
    top = pdf.get_y()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    png = io.BytesIO()
    img.save(png, format="PNG")
    png.seek(0)
    img_w = 45
    pdf.image(png, x=pdf.l_margin, y=top, w=img_w)
    img_bottom = top + img_w * img.height / img.width

    x0 = pdf.l_margin + img_w + 6
    pdf.set_xy(x0, top)
    label_w, value_w = 32, pdf.w - pdf.r_margin - x0 - 32
    for label, value in summary:
        pdf.set_x(x0)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*GREY)
        pdf.cell(label_w, 6, latin1(label))
        pdf.set_font("Helvetica", "B" if label == "Severity" else "", 9.5)
        rgb = SEVERITY_RGB.get(severity, GREY) if label == "Severity" else (0, 0, 0)
        pdf.set_text_color(*rgb)
        pdf.multi_cell(value_w, 6, latin1(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(max(pdf.get_y(), img_bottom) + 4)

    # Body
    pdf.set_draw_color(200, 200, 200)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, latin1(body_title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    body = body_markdown
    if source_line:
        body = "\n".join(l for l in body.splitlines() if not l.strip().lower().startswith("source:"))
    _markdown_block(pdf, body)

    if source_line:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, latin1(source_line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 4, latin1(disclaimer), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())
