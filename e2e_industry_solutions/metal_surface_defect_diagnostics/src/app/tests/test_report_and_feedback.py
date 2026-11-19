"""Unit tests for lib/feedback.py (pure parts), lib/prompt.py helpers and lib/report_pdf.py."""

import io
import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import feedback, prompt, report_pdf  # noqa: E402

PRED = {
    "image_sha256": "ab" * 32,
    "image_file_name": "x.jpg",
    "predicted_class": "pitted_surface",
    "confidence": 0.58,
    "probabilities": {"pitted_surface": 0.58, "inclusion": 0.40},
    "severity": "Low (unconfirmed)",
    "human_review_required": True,
    "review_reasons": ["Confidence 58% is below the 70% threshold."],
    "playbook_refs": "Source: PB-NEU-PIT v1.0.0; PB-NEU-INC v1.0.0",
    "classifier_endpoint": "ep",
    "report_text": "### Defect Summary\nText",
}
ENTRY = {
    "playbook_id": "PB-1", "playbook_version": "1.0.0", "display_name": "Pitted surface", "category": "Pitting",
    "description": "Small cavities \u2013 local attack", "visual_indicators": ["dark spots"],
    "typical_root_causes": ["chlorides"], "risk_assessment": "Structural", "progression_if_untreated": "Leaks",
    "recommended_inspection": ["UT"], "recommended_repair": ["Re-coat"], "monitoring": "Shorter interval",
    "escalation_criteria": ["Depth \u2265 limit"],
}


def test_rating_record():
    r = feedback.build_record(feedback_type="rating", submitted_by="a@b.c", prediction=PRED, rating="down")
    assert r["rating"] == "down" and r["verdict"] is None and r["confidence"] == 0.58
    assert set(r) == set(feedback.COLUMNS)
    assert '"inclusion": 0.4' in r["probabilities"]


def test_expert_review_rules():
    r = feedback.build_record(feedback_type="expert_review", submitted_by=None, prediction=PRED, verdict="confirmed")
    assert r["corrected_class"] == "pitted_surface"
    r = feedback.build_record(
        feedback_type="expert_review", submitted_by=None, prediction=PRED, verdict="corrected",
        corrected_class="inclusion", notes="  ",
    )
    assert r["corrected_class"] == "inclusion" and r["notes"] is None
    with pytest.raises(ValueError):
        feedback.build_record(feedback_type="expert_review", submitted_by=None, prediction=PRED, verdict="corrected")
    with pytest.raises(ValueError):
        feedback.build_record(feedback_type="rating", submitted_by=None, prediction=PRED, rating="meh")
    with pytest.raises(ValueError):
        feedback.build_record(feedback_type="other", submitted_by=None, prediction=PRED)


def test_review_request_and_case_id():
    r = feedback.build_record(
        feedback_type="review_request", submitted_by="a@b.c", prediction={**PRED, "case_id": "case-1"}, notes="why"
    )
    assert r["feedback_type"] == "review_request" and r["case_id"] == "case-1" and r["verdict"] is None
    assert r["review_reasons"] == "Confidence 58% is below the 70% threshold."
    # A stored case row carries review_reasons as a string; it must not be split into characters.
    row = {**PRED, "review_reasons": "Low confidence.", "case_id": "case-1"}
    r = feedback.build_record(feedback_type="expert_review", submitted_by=None, prediction=row, verdict="inconclusive")
    assert r["review_reasons"] == "Low confidence." and r["case_id"] == "case-1"


def test_case_statements():
    o = feedback.open_cases_statement("c.s.t", 30)
    assert "feedback_type = 'review_request'" in o and "NOT EXISTS" in o and o.endswith("LIMIT 30")
    rv = feedback.reviewed_cases_statement("c.s.t", 5)
    assert "feedback_type = 'expert_review'" in rv and "LEFT JOIN" in rv and rv.endswith("LIMIT 5")
    with pytest.raises(ValueError):
        feedback.open_cases_statement("c.s.t; DROP", 1)


def test_insert_statement_and_params():
    sql = feedback.insert_statement("c.s.diagnosis_feedback")
    assert sql.startswith("INSERT INTO `c`.`s`.`diagnosis_feedback` (submitted_at, feedback_id")
    assert ":report_text, :case_id)" in sql
    assert feedback._param("confidence", 0.5).type == "DOUBLE"
    assert feedback._param("human_review_required", True).value == "true"
    assert feedback._param("notes", None).value is None
    # Databricks Apps passes a VOLUME resource as its path; the dotted form is accepted too.
    assert feedback.volume_path("/Volumes/c/s/raw") == "/Volumes/c/s/raw"
    assert feedback.volume_path("/Volumes/c/s/raw/") == "/Volumes/c/s/raw"
    assert feedback.volume_path("c.s.raw") == "/Volumes/c/s/raw"
    for bad in ("c.s", "/Volumes/c/s", "/Volumes/c/s/raw/extra", "/Volumes/c/s/r;x"):
        with pytest.raises(ValueError):
            feedback.volume_path(bad)


def test_prompt_helpers():
    assert prompt.normalize_headings("### A\ntext\n# B") == "#### A\ntext\n#### B"
    md = prompt.entry_markdown(ENTRY)
    assert md.startswith("#### Pitted surface - Pitting") and "- UT" in md


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("L", (200, 200), 128).save(buf, format="BMP")
    return buf.getvalue()


@pytest.mark.parametrize("review", [True, False])
def test_pdf_builds(review):
    body = "### Defect Summary\n**Bold** text \u2013 dash\n- bullet \u2265 1\n  + nested\n1. step\nSource: PB-1 v1.0.0"
    pdf = report_pdf.build_pdf(
        generated_at="2026-11-18 10:00 UTC", file_name="x.bmp", image_bytes=_png(),
        summary=[("Predicted defect", "Pitted surface"), ("Severity", "Critical")], severity="Critical",
        human_review=review, review_reasons=("Confidence below threshold.",), body_title="Diagnostic report",
        body_markdown=body + "\n\n" + prompt.entry_markdown(ENTRY), source_line="Source: PB-1 v1.0.0",
        disclaimer="POC \u2013 not for operations",
    )
    assert pdf[:5] == b"%PDF-" and len(pdf) > 2000
