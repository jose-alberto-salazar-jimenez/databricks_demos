"""Severity and human-review rules (pure functions, no Databricks dependencies).

Rules (ARCHITECTURE.md section 5.2):

* top-1 confidence < threshold      -> "Low (unconfirmed)", human review, report covers top-2
* confidence >= threshold            -> the playbook base severity (Low / Medium / High)
* confidence >= 0.95 and base High   -> "Critical"
* no playbook entry or lookup failure -> human review and the LLM is not called; severity is
  "Unassessed" unless the low-confidence rule already applies
"""

from __future__ import annotations

from dataclasses import dataclass

BASE_LEVELS = ("Low", "Medium", "High")
LOW_UNCONFIRMED = "Low (unconfirmed)"
UNASSESSED = "Unassessed"
CRITICAL = "Critical"
CRITICAL_CONFIDENCE = 0.95


@dataclass(frozen=True)
class Assessment:
    severity: str
    human_review: bool
    reasons: tuple[str, ...]
    report_classes: tuple[str, ...]  # classes the diagnostic report should cover
    call_llm: bool


def top_k(probabilities: dict[str, float], k: int = 3) -> list[tuple[str, float]]:
    """Classes sorted by probability, highest first (ties broken by class name)."""
    return sorted(probabilities.items(), key=lambda kv: (-kv[1], kv[0]))[:k]


def normalize_base_severity(value: str | None) -> str | None:
    """Return Low/Medium/High, or None when the value is missing or not a known level."""
    if value is None:
        return None
    v = str(value).strip().capitalize()
    return v if v in BASE_LEVELS else None


def assess(
    predicted_class: str,
    confidence: float,
    threshold: float,
    base_severity: str | None,
    runner_up: str | None = None,
) -> Assessment:
    """Severity, human-review flag and report scope for one prediction.

    base_severity is the playbook `base_severity` of the predicted class, or None when there is
    no playbook entry or the lookup failed.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0, 1], got {threshold}")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be in [0, 1], got {confidence}")

    reasons: list[str] = []
    base = normalize_base_severity(base_severity)
    low_confidence = confidence < threshold

    if base is None:
        detail = "no playbook entry" if base_severity is None else f"invalid base severity {base_severity!r}"
        reasons.append(f"Playbook lookup for '{predicted_class}' gave {detail}; the AI report is skipped.")
    if low_confidence:
        reasons.append(f"Confidence {confidence:.0%} is below the {threshold:.0%} threshold.")

    if low_confidence:
        severity = LOW_UNCONFIRMED
    elif base is None:
        severity = UNASSESSED
    elif base == "High" and confidence >= CRITICAL_CONFIDENCE:
        severity = CRITICAL
    else:
        severity = base

    if low_confidence and runner_up and runner_up != predicted_class:
        report_classes = (predicted_class, runner_up)
    else:
        report_classes = (predicted_class,)

    return Assessment(
        severity=severity,
        human_review=low_confidence or base is None,
        reasons=tuple(reasons),
        report_classes=report_classes,
        call_llm=base is not None,
    )
