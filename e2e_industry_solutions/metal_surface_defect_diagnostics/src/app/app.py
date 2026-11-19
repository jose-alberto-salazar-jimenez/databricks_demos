"""Metal Surface Defect Diagnostics - Streamlit Databricks App (mobile-first layout).

One image per analysis: capture or upload -> Analyze -> result card and tabs -> actions
(PDF download, quick rating, expert review) -> New analysis.
Pipeline: classifier endpoint -> severity / human-review rules -> playbook lookup (SQL warehouse)
-> grounded report (Foundation Model API). All Databricks calls use the app's service principal.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import io
import os
import uuid

import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from PIL import Image, UnidentifiedImageError

from lib import classifier_client, feedback, llm_client, playbook, prompt, report_pdf, severity

MAX_UPLOAD_MB = 10
REQUIRED_ENV = ("CLASSIFIER_ENDPOINT", "LLM_ENDPOINT", "DATABRICKS_WAREHOUSE_ID", "PLAYBOOK_TABLE")
# severity -> (text colour, background)
SEVERITY_STYLE = {
    severity.CRITICAL: ("#ffffff", "#b71c1c"),
    "High": ("#b71c1c", "#ffebee"),
    "Medium": ("#e65100", "#fff3e0"),
    "Low": ("#1b5e20", "#e8f5e9"),
    severity.LOW_UNCONFIRMED: ("#424242", "#eeeeee"),
    severity.UNASSESSED: ("#424242", "#eeeeee"),
}
REVIEW_SEVERITIES = ("Low", "Medium", "High", "Critical")
VERDICT_LABELS = {
    "confirmed": "Confirm the prediction",
    "corrected": "Correct the defect class",
    "inconclusive": "Inconclusive - needs on-site inspection",
}
DISCLAIMER = (
    "Proof of concept. The classifier is trained on the NEU hot-rolled steel strip dataset, not on "
    "in-service pipeline photos, and the pipeline-corrosion interpretation is illustrative. Playbook "
    "content is a draft pending SME review and must not be used for operational decisions."
)

st.set_page_config(
    page_title="Defect Diagnostics",
    page_icon=":material/troubleshoot:",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Phone-width, app-like layout: one narrow column, app bar, cards, compact typography.
st.markdown(
    """
<style>
.block-container {max-width: 480px; padding: 0.75rem 1rem 3rem 1rem;}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {display: none;}
header[data-testid="stHeader"] {background: transparent;}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {
  font-size: 0.93rem; line-height: 1.45; overflow-wrap: anywhere;}
[data-testid="stMarkdownContainer"] h4 {font-size: 1.0rem; font-weight: 700; margin: 0.9rem 0 0.2rem 0; padding: 0;}
[data-testid="stMarkdownContainer"] code {white-space: pre-wrap; word-break: break-all; font-size: 0.8rem;}
.msd-appbar {background: #1565c0; color: #fff; border-radius: 14px; padding: 12px 16px; margin: 0 0 12px 0;}
.msd-appbar .t {font-size: 1.1rem; font-weight: 700; line-height: 1.25;}
.msd-appbar .s {font-size: 0.78rem; opacity: 0.85;}
.msd-step {font-size: 0.8rem; color: #757575; margin: 2px 0 6px 0;}
.msd-card {border: 1px solid #e0e0e0; border-radius: 14px; padding: 14px 16px; margin: 8px 0 10px 0;}
.msd-label {font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: #757575; margin-top: 4px;}
.msd-defect {font-size: 1.35rem; font-weight: 700; line-height: 1.2; overflow-wrap: anywhere;}
.msd-sub {font-size: 0.88rem; color: #424242; margin: 2px 0 4px 0;}
.msd-row {display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0 10px 0;}
.msd-chip {border-radius: 999px; padding: 3px 10px; font-size: 0.8rem; font-weight: 600;}
.msd-prob {display: flex; justify-content: space-between; font-size: 0.85rem; margin-top: 4px;}
.msd-bar {height: 8px; border-radius: 4px; background: #eeeeee; margin: 2px 0 6px 0;}
.msd-bar > div {height: 8px; border-radius: 4px; background: #1565c0;}
.msd-banner {border-radius: 12px; padding: 10px 12px; font-size: 0.88rem; line-height: 1.4; margin: 6px 0 10px 0;}
.msd-review {background: #fff3e0; color: #bf360c; border: 1px solid #ffcc80;}
</style>
""",
    unsafe_allow_html=True,
)


def display_name(defect_class: str, entries: dict) -> str:
    return entries.get(defect_class, {}).get("display_name") or defect_class.replace("_", " ").capitalize()


def current_user() -> str | None:
    """App user forwarded by Databricks Apps (identity of the person, not the service principal)."""
    headers = st.context.headers
    return headers.get("X-Forwarded-Email") or headers.get("X-Forwarded-Preferred-Username")


# ---------------------------------------------------------------------------- configuration
def load_config() -> dict:
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        st.error(
            f"Missing app configuration: {', '.join(missing)}. These come from the app resources "
            "declared in the bundle (resources/msd_app.app.yml); deploy the bundle to attach them."
        )
        st.stop()
    return {
        "classifier_endpoint": os.environ["CLASSIFIER_ENDPOINT"],
        "llm_endpoint": os.environ["LLM_ENDPOINT"],
        "warehouse_id": os.environ["DATABRICKS_WAREHOUSE_ID"],
        "playbook_table": os.environ["PLAYBOOK_TABLE"],
        "threshold": float(os.getenv("CONFIDENCE_THRESHOLD", "0.70")),
        # Optional: feedback is disabled (with a notice) when these resources are not attached.
        "feedback_table": os.getenv("FEEDBACK_TABLE"),
        "review_volume": os.getenv("REVIEW_VOLUME"),
    }


@st.cache_resource
def get_client() -> WorkspaceClient:
    # Generous HTTP timeout: the classifier endpoint scales to zero and cold-starts on first use.
    return WorkspaceClient(config=Config(http_timeout_seconds=300))


# ---------------------------------------------------------------------------- pipeline
def run_diagnosis(cfg: dict, image_bytes: bytes, file_name: str) -> dict:
    """Run the full diagnosis for one image; returns everything the UI needs."""
    w = get_client()
    result: dict = {
        "errors": [],
        "file_name": file_name,
        "image_bytes": image_bytes,
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "analysed_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "case_id": str(uuid.uuid4()),
    }

    with st.status("Analysing the image...", expanded=True) as status:
        st.write("Classifying (the first request after idle can take about a minute)...")
        try:
            pred = classifier_client.classify(w, cfg["classifier_endpoint"], image_bytes)
        except Exception as e:  # noqa: BLE001 - surfaced to the user
            status.update(label="Classification failed", state="error")
            result["fatal"] = f"Could not classify the image: {e}"
            return result
        result["prediction"] = pred
        ranked = severity.top_k(pred.probabilities, k=3)
        runner_up = ranked[1][0] if len(ranked) > 1 else None

        st.write("Retrieving the playbook entry...")
        wanted = [pred.predicted_class] + ([runner_up] if runner_up and pred.confidence < cfg["threshold"] else [])
        try:
            entries = playbook.fetch_entries(w, cfg["warehouse_id"], cfg["playbook_table"], wanted)
        except Exception as e:  # noqa: BLE001 - lookup failure routes to human review
            entries = {}
            result["errors"].append(f"Playbook lookup failed: {e}")
        result["entries"] = entries

        top_entry = entries.get(pred.predicted_class)
        assessment = severity.assess(
            predicted_class=pred.predicted_class,
            confidence=pred.confidence,
            threshold=cfg["threshold"],
            base_severity=top_entry.get("base_severity") if top_entry else None,
            runner_up=runner_up,
        )
        result["assessment"] = assessment

        report_entries = [entries[c] for c in assessment.report_classes if c in entries]
        result["report_entries"] = report_entries
        if assessment.call_llm and report_entries:
            st.write("Writing the grounded diagnostic report...")
            user_prompt = prompt.build_user_prompt(
                predicted_class=pred.predicted_class,
                category=top_entry.get("category") if top_entry else None,
                confidence=pred.confidence,
                severity=assessment.severity,
                human_review=assessment.human_review,
                review_reasons=assessment.reasons,
                entries=report_entries,
            )
            try:
                report = llm_client.generate_report(w, cfg["llm_endpoint"], prompt.SYSTEM_PROMPT, user_prompt)
                result["report"] = prompt.ensure_source_line(report, report_entries)
            except Exception as e:  # noqa: BLE001 - fall back to the reviewed playbook text
                result["errors"].append(f"AI report unavailable ({e}); showing the reviewed playbook entry instead.")
        result["source_line"] = prompt.source_line(report_entries) if report_entries else None

        # Snapshot of what the user saw; stored with any rating or expert review.
        result["record"] = {
            "image_sha256": result["image_sha256"],
            "image_file_name": file_name,
            "predicted_class": pred.predicted_class,
            "confidence": pred.confidence,
            "probabilities": pred.probabilities,
            "severity": assessment.severity,
            "human_review_required": assessment.human_review,
            "review_reasons": list(assessment.reasons),
            "playbook_refs": result["source_line"],
            "classifier_endpoint": cfg["classifier_endpoint"],
            "report_text": result.get("report"),
            "case_id": result["case_id"],
        }

        # Unconfirmed results go to the expert review queue automatically.
        if assessment.human_review and feedback_enabled(cfg):
            st.write("Opening an expert review case...")
            try:
                open_case(cfg, result, current_user(), notes="Opened automatically (unconfirmed result).")
            except Exception as e:  # noqa: BLE001 - the diagnosis itself is still usable
                result["errors"].append(f"Could not open the expert review case: {e}")

        st.write("Preparing the PDF report...")
        try:
            result["pdf"] = make_pdf(result)
        except Exception as e:  # noqa: BLE001 - the on-screen result is still usable
            result["errors"].append(f"PDF report unavailable: {e}")
        status.update(label="Analysis complete", state="complete", expanded=False)
    return result


def make_pdf(result: dict) -> bytes:
    pred, a, entries = result["prediction"], result["assessment"], result["entries"]
    top = entries.get(pred.predicted_class)
    summary = [
        ("Predicted defect", display_name(pred.predicted_class, entries)),
        ("Category", top.get("category") if top else "unknown"),
        ("Confidence", f"{pred.confidence:.1%}"),
        ("Severity", a.severity),
        ("Human review", "Required" if a.human_review else "Not required"),
        ("Top classes", ", ".join(f"{display_name(c, entries)} {p:.1%}" for c, p in severity.top_k(pred.probabilities, 3))),
    ]
    if len(a.report_classes) > 1:
        alt = a.report_classes[1]
        summary.insert(1, ("Alternative", f"{display_name(alt, entries)} ({pred.probabilities[alt]:.1%})"))
    if result.get("report"):
        title, body = "Diagnostic report", result["report"]
    elif result["report_entries"]:
        title = "Reviewed playbook entry"
        body = "\n\n".join(prompt.entry_markdown(e) for e in result["report_entries"])
    else:
        title = "No playbook entry"
        body = "No reviewed playbook entry exists for this prediction. Route the image to an integrity engineer."
    return report_pdf.build_pdf(
        generated_at=result["analysed_at"],
        file_name=result["file_name"],
        image_bytes=result["image_bytes"],
        summary=summary,
        severity=a.severity,
        human_review=a.human_review,
        review_reasons=a.reasons,
        body_title=title,
        body_markdown=body,
        source_line=result.get("source_line"),
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------------- rendering
def chip(text: str, fg: str = "#424242", bg: str = "#eeeeee") -> str:
    return f'<span class="msd-chip" style="color:{fg};background:{bg}">{html.escape(text)}</span>'


def prob_bars(probabilities: dict[str, float], entries: dict, k: int | None = None) -> str:
    rows = []
    for c, p in severity.top_k(probabilities, k or len(probabilities)):
        rows.append(
            f'<div class="msd-prob"><span>{html.escape(display_name(c, entries))}</span><span>{p:.1%}</span></div>'
            f'<div class="msd-bar"><div style="width:{max(p * 100, 0.5):.1f}%"></div></div>'
        )
    return "".join(rows)


def render_entry(entry: dict) -> None:
    meta = "".join(
        chip(t)
        for t in (
            f"{entry.get('playbook_id')} v{entry.get('playbook_version')}",
            f"Status: {entry.get('playbook_status')}",
            f"Approved by: {entry.get('approved_by')}",
            f"Reviewed {entry.get('last_reviewed')}",
            f"Base severity: {entry.get('base_severity')}",
        )
    )
    st.markdown(f'<div class="msd-row">{meta}</div>', unsafe_allow_html=True)
    st.markdown(prompt.entry_markdown(entry))
    if entry.get("disclaimer"):
        st.caption(entry["disclaimer"])


def render_card(cfg: dict, result: dict) -> None:
    pred, a, entries = result["prediction"], result["assessment"], result["entries"]
    top = entries.get(pred.predicted_class)
    fg, bg = SEVERITY_STYLE.get(a.severity, ("#424242", "#eeeeee"))
    unconfirmed = a.severity == severity.LOW_UNCONFIRMED
    alternative = ""
    if len(a.report_classes) > 1:
        alt = a.report_classes[1]
        alternative = (
            f'<div class="msd-sub">Alternative: <b>{html.escape(display_name(alt, entries))}</b> '
            f"({pred.probabilities[alt]:.1%})</div>"
        )
    review = (
        chip("Expert review required", "#bf360c", "#fff3e0")
        if a.human_review
        else chip("No review required", "#1b5e20", "#e8f5e9")
    )
    st.markdown(
        f'<div class="msd-card">'
        f'<div class="msd-label">{"Most likely defect (unconfirmed)" if unconfirmed else "Predicted defect"}</div>'
        f'<div class="msd-defect">{html.escape(display_name(pred.predicted_class, entries))}</div>'
        f'<div class="msd-sub">{html.escape(top.get("category") if top else "Category unknown")}</div>'
        f"{alternative}"
        f'<div class="msd-row">{chip("Severity: " + a.severity, fg, bg)}'
        f'{chip(f"Confidence {pred.confidence:.1%}", "#0d47a1", "#e3f2fd")}{review}</div>'
        f'<div class="msd-label">Top 3 classes</div>{prob_bars(pred.probabilities, entries, 3)}'
        f"</div>",
        unsafe_allow_html=True,
    )
    if a.human_review:
        st.markdown(
            f'<div class="msd-banner msd-review"><b>Unconfirmed result.</b> {html.escape(" ".join(a.reasons))} '
            "Do not act on this report until an integrity engineer confirms it: use <b>Expert review</b> below.</div>",
            unsafe_allow_html=True,
        )


def render_tabs(cfg: dict, result: dict) -> None:
    pred, a, entries = result["prediction"], result["assessment"], result["entries"]
    tab_report, tab_playbook, tab_model = st.tabs(["Report", "Playbook", "Model"])
    with tab_report:
        if result.get("report"):
            st.caption("AI-generated from the reviewed playbook entry only.")
            body = "\n".join(
                line for line in result["report"].splitlines() if not line.strip().lower().startswith("source:")
            )
            st.markdown(prompt.normalize_headings(body))
            st.caption(result["source_line"])
        elif not a.call_llm:
            st.info("No AI report: there is no reviewed playbook entry for this prediction. Route it to an integrity engineer.")
        elif result["report_entries"]:
            st.caption("AI report unavailable - reviewed playbook content shown instead.")
            for e in result["report_entries"]:
                st.markdown(prompt.entry_markdown(e))
    with tab_playbook:
        if result["report_entries"]:
            for i, e in enumerate(result["report_entries"]):
                if i:
                    st.divider()
                render_entry(e)
        else:
            st.info("No playbook entry found for this prediction.")
    with tab_model:
        st.markdown(f'<div class="msd-label">All classes</div>{prob_bars(pred.probabilities, entries)}', unsafe_allow_html=True)
        st.caption(
            f"Endpoint `{cfg['classifier_endpoint']}` - review threshold {cfg['threshold']:.0%} - "
            f"report covers: {', '.join(display_name(c, entries) for c in a.report_classes)}"
        )


def save_rating(cfg: dict, key: str) -> None:
    """st.feedback callback: store a thumbs up/down for the current result."""
    value = st.session_state.get(key)
    result = st.session_state.get("result")
    if value is None or not result:
        return
    try:
        record = feedback.build_record(
            feedback_type="rating",
            submitted_by=current_user(),
            prediction=result["record"],
            rating="up" if value == 1 else "down",
        )
        feedback.save(get_client(), cfg["warehouse_id"], cfg["feedback_table"], record)
        result["rated"] = "up" if value == 1 else "down"
    except Exception as e:  # noqa: BLE001 - shown on rerun
        result["rating_error"] = str(e)


def render_actions(cfg: dict, result: dict, n: int) -> None:
    pred, a, entries = result["prediction"], result["assessment"], result["entries"]
    if result.get("pdf"):
        stem = os.path.splitext(result["file_name"])[0][:40] or "image"
        st.download_button(
            "Download PDF report",
            data=result["pdf"],
            file_name=f"msd_report_{stem}_{result['analysed_at'][:10]}.pdf",
            mime="application/pdf",
            icon=":material/picture_as_pdf:",
            type="primary",
            width="stretch",
        )

    if not feedback_enabled(cfg):
        st.info("Feedback is disabled: the feedback-table / review-volume app resources are not attached.")
        return

    with st.container(border=True):
        st.markdown("**Was this diagnosis helpful?**")
        if result.get("rated"):
            msg = "Thanks, your rating was saved."
            if result["rated"] == "down":
                msg += " If the result looks wrong, use Send to expert review below."
            st.caption(msg)
        else:
            key = f"rate_{n}"
            st.feedback("thumbs", key=key, on_change=save_rating, args=(cfg, key))
        if result.get("rating_error"):
            st.error(f"Could not save the rating: {result['rating_error']}")

    # Diagnose only *requests* a review (opens a case). Verdicts are recorded on the Review cases
    # tab, so a request can never be mistaken for a final verdict.
    with st.expander("Send to expert review", expanded=a.human_review, icon=":material/engineering:"):
        if result.get("case_opened"):
            st.info(
                "This analysis is in the expert review queue. It stays under **Review cases > Open** "
                "until an integrity engineer records a verdict there.",
                icon=":material/pending_actions:",
            )
            return
        st.caption(
            "Not sure about this result? Send it to the expert review queue. An integrity engineer "
            "confirms or corrects it on the Review cases tab."
        )
        classes = [c for c, _ in severity.top_k(pred.probabilities, len(pred.probabilities))]
        with st.form(f"request_{n}", border=False):
            suspected = st.selectbox(
                "What do you think it is? (optional)",
                classes,
                index=None,
                format_func=lambda c: display_name(c, entries),
                placeholder="No opinion",
                key=f"request_{n}_suspected",
            )
            note = st.text_input("Note for the reviewer (optional)", max_chars=500, key=f"request_{n}_note")
            send = st.form_submit_button(
                "Send to expert review", type="primary", icon=":material/send:", width="stretch"
            )
        if send:
            parts = [f"Suspected defect: {display_name(suspected, entries)}."] if suspected else []
            parts.append(note.strip() or "Requested by the user.")
            try:
                with st.spinner("Opening the case..."):
                    open_case(cfg, result, current_user(), notes=" ".join(parts))
                st.rerun()
            except Exception as e:  # noqa: BLE001 - surfaced to the user
                st.error(f"Could not open the case: {e}")


# ---------------------------------------------------------------------------- review cases
def feedback_enabled(cfg: dict) -> bool:
    return bool(cfg["feedback_table"] and cfg["review_volume"])


def ensure_image_copy(cfg: dict, result: dict) -> str:
    """Copy the analysed image to the review volume once per analysis; returns its path."""
    if not result.get("image_path"):
        result["image_path"] = feedback.upload_image(
            get_client(), cfg["review_volume"], result["image_sha256"], result["file_name"], result["image_bytes"]
        )
    return result["image_path"]


def open_case(cfg: dict, result: dict, requested_by: str | None, notes: str | None) -> None:
    """Insert the review_request that puts this analysis in the expert review queue (once)."""
    if result.get("case_opened"):
        return
    record = feedback.build_record(
        feedback_type="review_request",
        submitted_by=requested_by,
        prediction=result["record"],
        notes=notes,
        image_path=ensure_image_copy(cfg, result),
    )
    feedback.save(get_client(), cfg["warehouse_id"], cfg["feedback_table"], record)
    result["case_opened"] = True
    load_cases.clear()


def review_form(cfg: dict, key: str, prediction: dict, classes: list[str], entries: dict, image_path_fn) -> str | None:
    """Expert review form (verdict, corrected class, severity, notes); returns the saved feedback_id."""
    # Explicit keys: several review forms can be on the page at once (Diagnose + each open case).
    with st.form(key, border=False):
        verdict = st.radio("Verdict", list(VERDICT_LABELS), format_func=VERDICT_LABELS.get, key=f"{key}_verdict")
        corrected = st.selectbox(
            "Actual defect (when correcting)",
            classes,
            index=None,
            format_func=lambda c: display_name(c, entries),
            placeholder="Select the actual defect",
            key=f"{key}_class",
        )
        reviewer_severity = st.selectbox(
            "Severity (reviewer)", REVIEW_SEVERITIES, index=None, placeholder="Optional", key=f"{key}_severity"
        )
        notes = st.text_area(
            "Notes", max_chars=2000, placeholder="Observations, measurements, next steps...", key=f"{key}_notes"
        )
        submitted = st.form_submit_button("Submit review", type="primary", width="stretch")
    if not submitted:
        return None
    if verdict == "corrected" and not corrected:
        st.error("Select the actual defect to submit a correction.")
        return None
    try:
        with st.spinner("Saving the review..."):
            record = feedback.build_record(
                feedback_type="expert_review",
                submitted_by=current_user(),
                prediction=prediction,
                verdict=verdict,
                corrected_class=corrected if verdict == "corrected" else None,
                corrected_severity=reviewer_severity,
                notes=notes,
                image_path=image_path_fn(),
            )
            saved = feedback.save(get_client(), cfg["warehouse_id"], cfg["feedback_table"], record)
        load_cases.clear()
        return saved
    except Exception as e:  # noqa: BLE001 - surfaced to the user
        st.error(f"Could not save the review: {e}")
        return None


@st.cache_data(ttl=60, show_spinner=False)
def load_cases(table: str, warehouse_id: str) -> dict[str, list[dict]]:
    return feedback.list_cases(get_client(), warehouse_id, table)


@st.cache_data(max_entries=64, show_spinner=False)
def load_image(path: str) -> bytes:
    return feedback.download_image(get_client(), path)


def case_card(case: dict, status_chip: str, extra: str = "") -> str:
    fg, bg = SEVERITY_STYLE.get(case.get("severity"), ("#424242", "#eeeeee"))
    conf = case.get("confidence")
    return (
        f'<div class="msd-card">'
        f'<div class="msd-label">{html.escape(case.get("image_file_name") or "image")} - '
        f'{html.escape((case.get("requested_at") or case.get("submitted_at") or "")[:16])} UTC</div>'
        f'<div class="msd-defect" style="font-size:1.1rem">{html.escape(display_name(case.get("predicted_class") or "?", {}))}</div>'
        f'<div class="msd-row">{status_chip}{chip("Severity: " + (case.get("severity") or "?"), fg, bg)}'
        f'{chip(f"Confidence {conf:.1%}" if conf is not None else "Confidence ?", "#0d47a1", "#e3f2fd")}</div>'
        f"{extra}</div>"
    )


def case_details(case: dict) -> None:
    """Image, model output and AI report of a case (inside its expander)."""
    t_img, t_model, t_report = st.tabs(["Image", "Model", "Report"])
    with t_img:
        try:
            st.image(load_image(case["image_path"]), width="stretch")
        except Exception as e:  # noqa: BLE001 - missing copies should not break the list
            st.caption(f"Image unavailable: {e}")
    with t_model:
        if case.get("probabilities"):
            st.markdown(prob_bars(case["probabilities"], {}), unsafe_allow_html=True)
        if case.get("review_reasons"):
            st.caption(case["review_reasons"])
    with t_report:
        if case.get("report_text"):
            st.markdown(prompt.normalize_headings(case["report_text"]))
        else:
            st.caption("No AI report was generated for this analysis.")


def render_cases(cfg: dict) -> None:
    if not feedback_enabled(cfg):
        st.info("Review cases are disabled: the feedback-table / review-volume app resources are not attached.")
        return
    try:
        cases = load_cases(cfg["feedback_table"], cfg["warehouse_id"])
    except Exception as e:  # noqa: BLE001 - surfaced to the user
        st.error(f"Could not load the review cases: {e}")
        return
    counts = {"open": len(cases["open"]), "reviewed": len(cases["reviewed"])}
    view = st.radio(
        "Cases",
        ["open", "reviewed"],
        format_func=lambda v: f"{v.capitalize()} ({counts[v]})",
        horizontal=True,
        key="case_view",
        label_visibility="collapsed",
    )
    st.button("Refresh", icon=":material/refresh:", on_click=load_cases.clear, key="cases_refresh")
    st.caption("Newest first, up to 30 per list. Unconfirmed results open a case automatically.")

    if view == "open":
        if not cases["open"]:
            st.success("No open cases - the review queue is empty.", icon=":material/done_all:")
        for case in cases["open"]:
            requested = f'<div class="msd-sub">Requested by {html.escape(case.get("submitted_by") or "unknown")}'
            requested += f": {html.escape(case['notes'])}</div>" if case.get("notes") else "</div>"
            st.markdown(case_card(case, chip("Open", "#bf360c", "#fff3e0"), requested), unsafe_allow_html=True)
            with st.expander("Review this case", icon=":material/engineering:"):
                case_details(case)
                classes = [c for c, _ in severity.top_k(case["probabilities"], len(case["probabilities"]))] or [
                    case["predicted_class"]
                ]
                saved = review_form(
                    cfg, f"case_{case['case_id']}", case, classes, {}, lambda case=case: case.get("image_path")
                )
                if saved:
                    st.toast("Review saved - case closed.", icon=":material/task_alt:")
                    st.rerun()
    else:
        if not cases["reviewed"]:
            st.info("No reviewed cases yet.")
        for case in cases["reviewed"]:
            verdict = case.get("verdict") or "?"
            style = {"confirmed": ("#1b5e20", "#e8f5e9"), "corrected": ("#4a148c", "#f3e5f5")}.get(
                verdict, ("#424242", "#eeeeee")
            )
            outcome = f"Verdict: <b>{html.escape(verdict)}</b>"
            if verdict == "corrected" and case.get("corrected_class"):
                outcome += f" to <b>{html.escape(display_name(case['corrected_class'], {}))}</b>"
            if case.get("corrected_severity"):
                outcome += f" - reviewer severity <b>{html.escape(case['corrected_severity'])}</b>"
            outcome += (
                f"<br>Reviewed by {html.escape(case.get('submitted_by') or 'unknown')} on "
                f"{html.escape((case.get('submitted_at') or '')[:16])} UTC"
            )
            extra = f'<div class="msd-sub">{outcome}</div>'
            st.markdown(case_card(case, chip("Reviewed", *style)), unsafe_allow_html=True)
            st.markdown(extra, unsafe_allow_html=True)
            with st.expander("Details", icon=":material/description:"):
                if case.get("notes"):
                    st.markdown(f"**Reviewer notes:** {case['notes']}")
                if case.get("requested_at"):
                    st.caption(
                        f"Case opened by {case.get('requested_by') or 'unknown'} on {case['requested_at'][:16]} UTC"
                    )
                else:
                    st.caption("Reviewed directly from the analysis (no queued request).")
                case_details(case)


# ---------------------------------------------------------------------------- page
def new_analysis() -> None:
    """Discard the current result; new widget keys give an empty uploader / camera."""
    st.session_state["n"] = st.session_state.get("n", 0) + 1
    st.session_state.pop("result", None)


def read_image(file) -> tuple[bytes, Image.Image] | None:
    data = file.getvalue()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        st.error(f"The file is larger than {MAX_UPLOAD_MB} MB.")
        return None
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError):
        st.error("The file could not be read as an image.")
        return None
    return data, image


cfg = load_config()
st.session_state.setdefault("n", 0)
n = st.session_state["n"]

st.markdown(
    '<div class="msd-appbar"><div class="t">Metal Surface Defect Diagnostics</div>'
    '<div class="s">Pipe corrosion image diagnostics - POC</div></div>',
    unsafe_allow_html=True,
)

tab_diagnose, tab_cases = st.tabs(["Diagnose", "Review cases"])

with tab_diagnose:
    result = st.session_state.get("result")
    if result is None:
        # Step 1: exactly one image (upload or camera); nothing is sent until Analyze is pressed.
        st.markdown('<div class="msd-step">Step 1 of 2 - add one photo of the metal surface</div>', unsafe_allow_html=True)
        source = st.segmented_control(
            "Image source",
            ["Upload", "Camera"],
            default="Upload",
            key=f"src_{n}",
            label_visibility="collapsed",
            width="stretch",
        )
        if source == "Camera":
            file = st.camera_input("Take a photo", key=f"cam_{n}", label_visibility="collapsed")
        else:
            file = st.file_uploader(
                "Upload a photo",
                type=["jpg", "jpeg", "png", "bmp"],
                accept_multiple_files=False,
                key=f"up_{n}",
                label_visibility="collapsed",
            )
        if file is None:
            st.caption(f"JPG, PNG or BMP up to {MAX_UPLOAD_MB} MB. One image per analysis.")
        else:
            loaded = read_image(file)
            if loaded:
                data, image = loaded
                st.image(image, caption=file.name, width="stretch")
                st.markdown('<div class="msd-step">Step 2 of 2 - analyse it</div>', unsafe_allow_html=True)
                if st.button("Analyze image", type="primary", icon=":material/troubleshoot:", width="stretch"):
                    st.session_state["result"] = run_diagnosis(cfg, data, file.name)
                    st.rerun()
    else:
        if "fatal" in result:
            st.error(result["fatal"])
        else:
            st.image(
                result["image_bytes"], caption=f"{result['file_name']} - analysed {result['analysed_at']}", width="stretch"
            )
            for msg in result["errors"]:
                st.warning(msg)
            render_card(cfg, result)
            render_tabs(cfg, result)
            render_actions(cfg, result, n)
        st.button("New analysis", icon=":material/add_a_photo:", on_click=new_analysis, width="stretch")

with tab_cases:
    render_cases(cfg)

with st.expander("About this app", icon=":material/info:"):
    st.markdown(
        "Classifies the defect in one photo, assigns a severity, and writes a diagnostic report grounded "
        "on the engineer-reviewed defect playbook. Results below "
        f"{cfg['threshold']:.0%} confidence, or without a playbook entry, are marked unconfirmed and "
        "routed to expert review."
    )
    st.markdown(
        f"- Classifier: `{cfg['classifier_endpoint']}`\n"
        f"- LLM: `{cfg['llm_endpoint']}`\n"
        f"- Playbook: `{cfg['playbook_table']}`"
    )
    st.caption(DISCLAIMER)
