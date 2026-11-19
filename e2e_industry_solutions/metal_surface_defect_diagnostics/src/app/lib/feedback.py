"""Human-in-the-loop store: quick ratings, review cases and expert reviews.

Each submission is one row in `diagnosis_feedback` (INSERT through the SQL warehouse with named,
typed parameters). Every analysis has a `case_id`:

* `review_request` - opens a case (automatically for unconfirmed results, or on user request);
* `expert_review`  - closes the case with a verdict (confirmed / corrected / inconclusive);
* `rating`         - thumbs up / down, independent of cases.

A case is open while it has a review_request and no expert_review. For requests and reviews the
image is copied to the raw volume under `reviews/<yyyy-mm-dd>/` so the reviewer can see it and
corrected labels can feed monitoring and future retraining.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import uuid

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

from lib.playbook import quote_table, run_statement

FEEDBACK_TYPES = ("rating", "review_request", "expert_review")
RATINGS = ("up", "down")
VERDICTS = ("confirmed", "corrected", "inconclusive")

# column -> SQL parameter type (None = STRING). submitted_at is set server-side.
COLUMNS: dict[str, str | None] = {
    "feedback_id": None,
    "submitted_by": None,
    "feedback_type": None,
    "rating": None,
    "verdict": None,
    "corrected_class": None,
    "corrected_severity": None,
    "notes": None,
    "image_sha256": None,
    "image_file_name": None,
    "image_path": None,
    "predicted_class": None,
    "confidence": "DOUBLE",
    "probabilities": None,
    "severity": None,
    "human_review_required": "BOOLEAN",
    "review_reasons": None,
    "playbook_refs": None,
    "classifier_endpoint": None,
    "report_text": None,
    "case_id": None,
}


def build_record(
    *,
    feedback_type: str,
    submitted_by: str | None,
    prediction: dict,
    rating: str | None = None,
    verdict: str | None = None,
    corrected_class: str | None = None,
    corrected_severity: str | None = None,
    notes: str | None = None,
    image_path: str | None = None,
    case_id: str | None = None,
) -> dict:
    """Validated row for diagnosis_feedback (pure).

    prediction keys: image_sha256, image_file_name, predicted_class, confidence, probabilities (dict),
    severity, human_review_required, review_reasons (list), playbook_refs, classifier_endpoint,
    report_text.
    """
    if feedback_type not in FEEDBACK_TYPES:
        raise ValueError(f"feedback_type must be one of {FEEDBACK_TYPES}")
    if feedback_type == "rating" and rating not in RATINGS:
        raise ValueError(f"rating must be one of {RATINGS}")
    if feedback_type == "expert_review":
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}")
        if verdict == "corrected" and not corrected_class:
            raise ValueError("corrected_class is required when the verdict is 'corrected'")
    if verdict == "confirmed":
        corrected_class = prediction["predicted_class"]
    reasons = prediction.get("review_reasons")
    if isinstance(reasons, (list, tuple)):  # live analysis: list; stored case row: already a string
        reasons = " ".join(reasons)
    return {
        "feedback_id": str(uuid.uuid4()),
        "submitted_by": submitted_by,
        "feedback_type": feedback_type,
        "rating": rating,
        "verdict": verdict,
        "corrected_class": corrected_class,
        "corrected_severity": corrected_severity,
        "notes": (notes or "").strip() or None,
        "image_sha256": prediction.get("image_sha256"),
        "image_file_name": prediction.get("image_file_name"),
        "image_path": image_path,
        "predicted_class": prediction.get("predicted_class"),
        "confidence": prediction.get("confidence"),
        "probabilities": json.dumps(prediction.get("probabilities") or {}),
        "severity": prediction.get("severity"),
        "human_review_required": prediction.get("human_review_required"),
        "review_reasons": reasons or None,
        "playbook_refs": prediction.get("playbook_refs"),
        "classifier_endpoint": prediction.get("classifier_endpoint"),
        "report_text": prediction.get("report_text"),
        "case_id": case_id or prediction.get("case_id"),
    }


def _param(name: str, value) -> StatementParameterListItem:
    sql_type = COLUMNS[name]
    if value is None:
        return StatementParameterListItem(name=name, type=sql_type)  # omitted value -> NULL
    if sql_type == "BOOLEAN":
        value = "true" if value else "false"
    return StatementParameterListItem(name=name, value=str(value), type=sql_type)


def insert_statement(table: str) -> str:
    cols = list(COLUMNS)
    return (
        f"INSERT INTO {quote_table(table)} (submitted_at, {', '.join(cols)}) "
        f"VALUES (current_timestamp(), {', '.join(':' + c for c in cols)})"
    )


def save(w: WorkspaceClient, warehouse_id: str, table: str, record: dict) -> str:
    """Insert one record; returns its feedback_id."""
    params = [_param(c, record.get(c)) for c in COLUMNS]
    run_statement(w, warehouse_id, insert_statement(table), params)
    return record["feedback_id"]


def volume_path(volume: str) -> str:
    """Normalise the review-volume value to /Volumes/catalog/schema/volume (validated).

    Databricks Apps resolves a VOLUME resource (`valueFrom: review-volume`) to its path
    (/Volumes/c/s/v); the dotted form c.s.v is accepted too.
    """
    value = volume.strip().rstrip("/")
    if value.startswith("/Volumes/"):
        dotted = value[len("/Volumes/"):].replace("/", ".")
    else:
        dotted = value
    quote_table(dotted, kind="volume")  # same three-part identifier rules
    return "/Volumes/" + dotted.replace(".", "/")


def upload_image(
    w: WorkspaceClient, volume_full_name: str, image_sha256: str, file_name: str, data: bytes
) -> str:
    """Copy the reviewed image to <volume>/reviews/<date>/<sha16><ext>; returns the path."""
    ext = os.path.splitext(file_name or "")[1].lower() or ".jpg"
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    path = f"{volume_path(volume_full_name)}/reviews/{day}/{image_sha256[:16]}{ext}"
    w.files.upload(path, io.BytesIO(data), overwrite=True)
    return path


def download_image(w: WorkspaceClient, path: str) -> bytes:
    return w.files.download(path).contents.read()


# ---------------------------------------------------------------------------- review cases
_CASE_FIELDS = (
    "case_id, feedback_id, CAST(submitted_at AS STRING) AS submitted_at, submitted_by, image_sha256, "
    "image_file_name, image_path, classifier_endpoint, predicted_class, confidence, probabilities, severity, human_review_required, "
    "review_reasons, playbook_refs, report_text, notes"
)


def open_cases_statement(table: str, limit: int) -> str:
    t = quote_table(table)
    return (
        f"SELECT {_CASE_FIELDS} FROM {t} r "
        f"WHERE r.feedback_type = 'review_request' AND NOT EXISTS ("
        f"SELECT 1 FROM {t} e WHERE e.feedback_type = 'expert_review' AND e.case_id = r.case_id) "
        f"QUALIFY row_number() OVER (PARTITION BY r.case_id ORDER BY r.submitted_at) = 1 "
        f"ORDER BY r.submitted_at DESC LIMIT {int(limit)}"
    )


def reviewed_cases_statement(table: str, limit: int) -> str:
    t = quote_table(table)
    return (
        f"SELECT COALESCE(e.case_id, e.feedback_id) AS case_id, e.feedback_id, "
        f"CAST(e.submitted_at AS STRING) AS submitted_at, e.submitted_by, e.image_sha256, e.image_file_name, "
        f"e.image_path, e.classifier_endpoint, "
        f"e.predicted_class, e.confidence, e.probabilities, e.severity, e.human_review_required, "
        f"e.review_reasons, e.playbook_refs, e.report_text, e.notes, e.verdict, e.corrected_class, "
        f"e.corrected_severity, r.submitted_by AS requested_by, CAST(r.submitted_at AS STRING) AS requested_at "
        f"FROM {t} e LEFT JOIN (SELECT * FROM {t} WHERE feedback_type = 'review_request' "
        f"QUALIFY row_number() OVER (PARTITION BY case_id ORDER BY submitted_at) = 1) r ON r.case_id = e.case_id "
        f"WHERE e.feedback_type = 'expert_review' ORDER BY e.submitted_at DESC LIMIT {int(limit)}"
    )


def _rows(response) -> list[dict]:
    columns = [c.name for c in response.manifest.schema.columns]
    rows = (response.result.data_array if response.result else None) or []
    out = []
    for row in rows:
        d = dict(zip(columns, row))
        if d.get("confidence") is not None:
            d["confidence"] = float(d["confidence"])
        if d.get("human_review_required") is not None:
            d["human_review_required"] = str(d["human_review_required"]).lower() == "true"
        probs = d.get("probabilities")
        d["probabilities"] = json.loads(probs) if probs else {}
        out.append(d)
    return out


def list_cases(w: WorkspaceClient, warehouse_id: str, table: str, limit: int = 30) -> dict[str, list[dict]]:
    """{'open': [...], 'reviewed': [...]}, newest first."""
    return {
        "open": _rows(run_statement(w, warehouse_id, open_cases_statement(table, limit), [])),
        "reviewed": _rows(run_statement(w, warehouse_id, reviewed_cases_statement(table, limit), [])),
    }
