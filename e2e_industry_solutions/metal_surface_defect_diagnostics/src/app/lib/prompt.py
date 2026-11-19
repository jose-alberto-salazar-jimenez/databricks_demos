"""Grounded prompt construction.

The LLM only rephrases and adapts the reviewed playbook entry (or entries, for low-confidence
results) to the prediction context. It must not add facts and must end with a source line.
"""

from __future__ import annotations

import re

SECTIONS = (
    "Defect Summary",
    "Risk Assessment",
    "Recommended Inspection",
    "Recommended Repair",
    "Monitoring and Escalation",
)

SYSTEM_PROMPT = f"""You are an assistant that writes short diagnostic reports for pipeline integrity engineers.

Grounding rules:
- Use ONLY the information in the PLAYBOOK ENTRY blocks and the PREDICTION CONTEXT provided by the user.
- Do not add facts, standards, numbers, causes or actions that are not in the playbook entries.
- If information for a section is missing from the playbook, write "Not covered by the playbook."
- State the model confidence and severity exactly as given. If human review is required, say so
  clearly at the start of the Defect Summary and explain why (low confidence or missing playbook).
- If two playbook entries are provided (low confidence), present the most likely class first and the
  runner-up as an alternative, and recommend confirming which one applies before acting.

Format (Markdown):
- Exactly these sections, in this order, each as a level-3 heading: {', '.join(SECTIONS)}.
- Use short bullet points for inspection, repair and escalation steps.
- Keep the report under 350 words.
- End with one final line, exactly as given in REQUIRED SOURCE LINE, and nothing after it.
"""


def format_entry(entry: dict) -> str:
    def bullets(items):
        return "\n".join(f"  - {item}" for item in (items or [])) or "  - (none)"

    return (
        f"playbook_id: {entry.get('playbook_id')}\n"
        f"playbook_version: {entry.get('playbook_version')}\n"
        f"defect_class: {entry.get('defect_class')}\n"
        f"display_name: {entry.get('display_name')}\n"
        f"category: {entry.get('category')}\n"
        f"base_severity: {entry.get('base_severity')}\n"
        f"description: {entry.get('description')}\n"
        f"visual_indicators:\n{bullets(entry.get('visual_indicators'))}\n"
        f"typical_root_causes:\n{bullets(entry.get('typical_root_causes'))}\n"
        f"risk_assessment: {entry.get('risk_assessment')}\n"
        f"progression_if_untreated: {entry.get('progression_if_untreated')}\n"
        f"recommended_inspection:\n{bullets(entry.get('recommended_inspection'))}\n"
        f"recommended_repair:\n{bullets(entry.get('recommended_repair'))}\n"
        f"monitoring: {entry.get('monitoring')}\n"
        f"escalation_criteria:\n{bullets(entry.get('escalation_criteria'))}"
    )


def source_line(entries: list[dict]) -> str:
    refs = "; ".join(f"{e.get('playbook_id')} v{e.get('playbook_version')}" for e in entries)
    return f"Source: {refs}"


def build_user_prompt(
    predicted_class: str,
    category: str | None,
    confidence: float,
    severity: str,
    human_review: bool,
    review_reasons: tuple[str, ...],
    entries: list[dict],
) -> str:
    reasons = "; ".join(review_reasons) if review_reasons else "none"
    blocks = "\n\n".join(
        f"PLAYBOOK ENTRY {i + 1}:\n{format_entry(e)}" for i, e in enumerate(entries)
    )
    return (
        "PREDICTION CONTEXT:\n"
        f"predicted_class: {predicted_class}\n"
        f"category: {category or 'unknown'}\n"
        f"confidence: {confidence:.1%}\n"
        f"severity: {severity}\n"
        f"human_review_required: {'yes' if human_review else 'no'}\n"
        f"review_reasons: {reasons}\n\n"
        f"{blocks}\n\n"
        f"REQUIRED SOURCE LINE:\n{source_line(entries)}\n\n"
        "Write the diagnostic report now."
    )


def normalize_headings(markdown: str, level: int = 4) -> str:
    """Rewrite every Markdown heading to one level (keeps report headings compact on screen)."""
    return re.sub(r"^\s{0,3}#{1,6}\s+", "#" * level + " ", markdown, flags=re.MULTILINE)


def entry_markdown(entry: dict) -> str:
    """Reviewed playbook entry as Markdown (shown when there is no AI report, and in the PDF)."""
    def bullets(items):
        return "\n".join(f"- {i}" for i in (items or [])) or "- (none)"

    return (
        f"#### {entry.get('display_name')} - {entry.get('category')}\n\n"
        f"{entry.get('description') or ''}\n\n"
        f"#### Visual indicators\n{bullets(entry.get('visual_indicators'))}\n\n"
        f"#### Typical root causes\n{bullets(entry.get('typical_root_causes'))}\n\n"
        f"#### Risk assessment\n{entry.get('risk_assessment') or ''}\n\n"
        f"**Progression if untreated:** {entry.get('progression_if_untreated') or ''}\n\n"
        f"#### Recommended inspection\n{bullets(entry.get('recommended_inspection'))}\n\n"
        f"#### Recommended repair\n{bullets(entry.get('recommended_repair'))}\n\n"
        f"#### Monitoring and escalation\n{entry.get('monitoring') or ''}\n\n"
        f"{bullets(entry.get('escalation_criteria'))}"
    )


def ensure_source_line(report: str, entries: list[dict]) -> str:
    """Guarantee the citation: replace a trailing Source line or append the required one."""
    required = source_line(entries)
    lines = report.rstrip().splitlines()
    if lines and lines[-1].strip().lower().startswith("source:"):
        lines = lines[:-1]
    return "\n".join(lines).rstrip() + "\n\n" + required
