import streamlit as st
import os
import base64
import json
import hashlib
import datetime
from io import BytesIO
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from dotenv import load_dotenv
from anthropic import Anthropic, NotFoundError
from pypdf import PdfReader

# ─── CONFIG ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HPE Expert Reviewer",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── API KEY ──────────────────────────────────────────────────────────────────
try:
    api_key = st.secrets.get("ANTHROPIC_API_KEY")
except Exception:
    api_key = None

if not api_key:
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    st.error("🚨 ANTHROPIC_API_KEY is missing. Add it to `.env` or Streamlit Secrets.")
    st.stop()

client = Anthropic(api_key=api_key)

# ─── MODELS ───────────────────────────────────────────────────────────────────
PRIMARY_MODEL  = "claude-opus-4-5"
FALLBACK_MODEL = "claude-sonnet-4-5"
CHAT_MODEL     = "claude-haiku-4-5-20251001"

JOURNALS = [
    "Medical Teacher",
    "BMC Medical Education",
    "Academic Medicine",
    "Medical Education",
    "JGME – Journal of Graduate Medical Education",
    "Teaching and Learning in Medicine",
    "Advances in Health Sciences Education",
]

REVIEW_CRITERIA = {
    "research_question": "Research question clarity & PICO/SPIDER framing",
    "methodology":       "Methodology rigor & reproducibility",
    "consort_srqr":      "CONSORT / SRQR / COREQ guideline adherence",
    "kirkpatrick":       "Kirkpatrick level outcomes achieved",
    "citations":         "Citation currency, completeness & in-text accuracy",
    "statistics":        "Statistical / qualitative data analysis soundness",
    "ethics":            "Ethical considerations & positionality",
    "golden_thread":     "Golden thread coherence (RQ → method → results → conclusion)",
}

# ─── SESSION STATE ─────────────────────────────────────────────────────────────
defaults = {
    "consent_given":   False,
    "pdf_base64":      None,
    "pdf_name":        "",
    "pdf_hash":        "",
    "pdf_text":        "",
    "report":          None,
    "raw_report":      "",
    "chat_history":    [],
    "model_used":      "",
    "session_start":   None,
    "upload_count":    0,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.session_start is None:
    st.session_state.session_start = datetime.datetime.utcnow()

# ─── CONSENT GATE ─────────────────────────────────────────────────────────────
if not st.session_state.consent_given:
    st.markdown(
        """
        <div style="max-width:620px;margin:4rem auto;padding:2rem;
             border:1px solid #e0ddd5;border-radius:12px;background:#fafaf7;">
          <h2 style="margin-top:0">🎓 HPE Expert Reviewer</h2>
          <h4 style="color:#555">Data &amp; Confidentiality Notice</h4>
          <p>Before using this tool, please read and accept the following:</p>
          <ul style="line-height:1.9">
            <li>Uploaded manuscripts are transmitted to <strong>Anthropic's API</strong>
                for AI analysis. Anthropic does <strong>not</strong> use API data to
                train their models. See
                <a href="https://www.anthropic.com/privacy" target="_blank">anthropic.com/privacy</a>.
            </li>
            <li>Documents are held <strong>in memory only</strong> for the duration of
                your session. They are <strong>never written to disk</strong> or stored
                by this application.</li>
            <li>Your session is automatically cleared when you close the browser tab.</li>
            <li><strong>Do not upload</strong> manuscripts containing identifiable patient
                data, unpublished clinical trial results under embargo, or any material
                covered by a confidentiality agreement that prohibits third-party
                processing.</li>
            <li>If your institution requires a Zero Data Retention (ZDR) agreement,
                contact
                <a href="https://www.anthropic.com/contact-sales" target="_blank">
                Anthropic directly</a> before use.</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        confirmed = st.checkbox(
            "I have read and understood the data notice above, and I confirm "
            "the manuscript I will upload does not contain restricted or "
            "patient-identifiable data."
        )
        if st.button("✅ Accept & Continue", disabled=not confirmed, use_container_width=True):
            st.session_state.consent_given = True
            st.rerun()
    st.stop()

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def encode_pdf(uploaded_file) -> tuple[str, str, str]:
    """Return (base64_string, plain_text_fallback, sha256_hash).
    Raw bytes never stored — only the base64 encoding needed for the API."""
    raw = uploaded_file.read()
    b64 = base64.standard_b64encode(raw).decode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    try:
        reader = PdfReader(BytesIO(raw))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception:
        text = ""
    return b64, text, sha


def clear_session_data():
    """Wipe all uploaded document data from session state."""
    sensitive_keys = [
        "pdf_base64", "pdf_name", "pdf_hash", "pdf_text",
        "report", "raw_report", "chat_history", "model_used",
    ]
    for k in sensitive_keys:
        st.session_state[k] = defaults[k]
    st.session_state.upload_count = 0


def build_system_prompt(journal: str) -> str:
    return (
        f"You are a Senior Editor and double-blind Peer Reviewer for '{journal}', "
        "one of the most rigorous journals in Health Professions Education (HPE). "
        "Your reviews are precise, evidence-based, and constructive. "
        "You quote exact passages from the manuscript to substantiate every criticism. "
        "You never fabricate content. "
        "You apply CONSORT for RCTs, SRQR for qualitative research, COREQ for interviews/focus groups, "
        "and always evaluate educational outcomes through Kirkpatrick's four-level framework. "
        "You scrutinise the 'golden thread': the logical chain from research question through "
        "methodology, results, and conclusion. "
        "You identify citation gaps, outdated references, and in-text vs reference-list mismatches."
    )


def build_review_prompt(selected_criteria: list[str], journal: str) -> str:
    criteria_block = "\n".join(
        f"  {i+1}. {REVIEW_CRITERIA[c]}"
        for i, c in enumerate(selected_criteria)
    )
    return f"""Perform a comprehensive peer review of this manuscript submitted to '{journal}'.

SELECTED REVIEW CRITERIA:
{criteria_block}

Return ONLY a valid JSON object — no markdown fences, no preamble — with exactly this schema:

{{
  "verdict": "Accept | Minor Revisions | Major Revisions | Reject",
  "overall_score": <integer 1-100>,
  "executive_summary": "<2-3 sentence overall assessment>",
  "scores": {{
    "novelty": <1-10>,
    "methodology": <1-10>,
    "clarity": <1-10>,
    "citations": <1-10>,
    "ethics": <1-10>
  }},
  "strengths": ["<strength 1>", "<strength 2>", "..."],
  "weaknesses": [
    {{
      "section": "Abstract|Introduction|Methods|Results|Discussion|Citations",
      "issue": "<specific issue — quote the manuscript text to prove the flaw>",
      "severity": "major|minor",
      "suggestion": "<concrete fix>"
    }}
  ],
  "section_comments": {{
    "abstract": "<comment>",
    "introduction": "<Does it identify the gap? Are citations current? Is the RQ explicit?>",
    "methods": "<Reproducibility, guideline adherence, sample size justification>",
    "results": "<Clarity, alignment with RQ, appropriate presentation>",
    "discussion": "<Overstating findings? Kirkpatrick level? Golden thread maintained?>"
  }},
  "golden_thread": "<Paragraph assessing RQ → methodology → results → conclusion coherence>",
  "kirkpatrick_level": {{
    "level": <1|2|3|4>,
    "justification": "<why this level>"
  }},
  "citation_audit": {{
    "missing_key_references": ["<Author Year — why relevant>"],
    "potentially_outdated": ["<citation — reason>"],
    "mismatches": "<in-text vs reference list issues, or 'None identified'>"
  }},
  "actionable_recommendations": [
    "<Numbered, specific action the authors must take>"
  ],
  "editor_note": "<Confidential note to the editor — not shared with authors>"
}}"""


def call_api_with_pdf(system: str, user_prompt: str, model: str) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": st.session_state.pdf_base64,
                    },
                },
                {"type": "text", "text": user_prompt},
            ],
        }],
    )
    return response.content[0].text


def call_api_with_text(system: str, user_prompt: str, model: str) -> str:
    text = st.session_state.pdf_text[:120_000]
    full_prompt = f"MANUSCRIPT TEXT:\n{text}\n\n{user_prompt}"
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": full_prompt}],
    )
    return response.content[0].text


def parse_report(raw: str) -> dict | None:
    try:
        start = raw.index("{")
        end   = raw.rindex("}") + 1
        return json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


def create_docx(report: dict | None, raw: str) -> bytes:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    heading = doc.add_heading("HPE Peer Review Report", 0)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Confidentiality footer on every page
    footer      = doc.sections[0].footer
    footer_para = footer.paragraphs[0]
    footer_para.text = (
        "CONFIDENTIAL — Generated by HPE Expert Reviewer. "
        "Processed via Anthropic API. Not for redistribution."
    )
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if report is None:
        doc.add_paragraph(raw)
    else:
        def h2(text):
            doc.add_heading(text, level=2)

        verdict = report.get("verdict", "—")
        score   = report.get("overall_score", "—")
        p = doc.add_paragraph()
        run = p.add_run(f"Verdict: {verdict}   |   Overall Score: {score}/100")
        run.bold = True
        run.font.size = Pt(13)
        run.font.color.rgb = RGBColor(0x1A, 0x3A, 0x4A)
        doc.add_paragraph(report.get("executive_summary", ""))

        h2("Dimension Scores")
        for k, v in report.get("scores", {}).items():
            doc.add_paragraph(f"{k.capitalize()}: {v}/10", style="List Bullet")

        kp = report.get("kirkpatrick_level", {})
        if kp:
            h2("Kirkpatrick Level")
            doc.add_paragraph(f"Level {kp.get('level','?')}: {kp.get('justification','')}")

        h2("Golden Thread Analysis")
        doc.add_paragraph(report.get("golden_thread", ""))

        h2("Strengths")
        for s in report.get("strengths", []):
            doc.add_paragraph(s, style="List Bullet")

        h2("Weaknesses")
        for w in report.get("weaknesses", []):
            sev = w.get("severity", "minor").upper()
            sec = w.get("section", "")
            doc.add_paragraph(
                f"[{sev} — {sec}] {w.get('issue','')}\n→ {w.get('suggestion','')}",
                style="List Bullet",
            )

        h2("Section-by-Section Comments")
        for sec, comment in report.get("section_comments", {}).items():
            p = doc.add_paragraph()
            p.add_run(sec.capitalize() + ": ").bold = True
            p.add_run(comment)

        h2("Citation Audit")
        ca = report.get("citation_audit", {})
        for ref in ca.get("missing_key_references", []):
            doc.add_paragraph(f"Missing: {ref}", style="List Bullet")
        for ref in ca.get("potentially_outdated", []):
            doc.add_paragraph(f"Outdated: {ref}", style="List Bullet")
        doc.add_paragraph(f"Mismatches: {ca.get('mismatches','None identified')}")

        h2("Actionable Recommendations")
        for i, rec in enumerate(report.get("actionable_recommendations", []), 1):
            doc.add_paragraph(f"{i}. {rec}")

        h2("Confidential Note to Editor")
        p = doc.add_paragraph(report.get("editor_note", ""))
        for run in p.runs:
            run.italic = True

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def render_verdict_badge(verdict: str) -> str:
    colours = {
        "accept": ("#d4edda", "#155724"),
        "minor":  ("#fff3cd", "#856404"),
        "major":  ("#f8d7da", "#721c24"),
        "reject": ("#f8d7da", "#491217"),
    }
    key = "minor"
    vl  = verdict.lower()
    if "reject" in vl:                                                   key = "reject"
    elif "major" in vl:                                                  key = "major"
    elif "accept" in vl and "minor" not in vl and "major" not in vl:    key = "accept"
    bg, fg = colours[key]
    return (
        f'<span style="background:{bg};color:{fg};padding:4px 14px;'
        f'border-radius:20px;font-weight:600;font-size:0.9rem;">{verdict}</span>'
    )


# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎓 HPE Expert Reviewer")
    st.caption("Powered by Claude · Multi-phase critical analysis")

    # ── Data protection status panel ──────────────────────────────────────────
    with st.expander("🔒 Data & Privacy Status", expanded=False):
        st.markdown(
            f"""
            | Item | Status |
            |---|---|
            | Consent given | ✅ Yes |
            | Files written to disk | ✅ Never |
            | API provider | Anthropic |
            | Training on API data | ✅ No |
            | Session started | {st.session_state.session_start.strftime('%H:%M UTC')} |
            | Documents processed | {st.session_state.upload_count} |
            """
        )
        if st.session_state.pdf_hash:
            st.caption(f"Current file SHA-256: `{st.session_state.pdf_hash[:16]}…`")
        st.markdown(
            "[Anthropic Privacy Policy](https://www.anthropic.com/privacy) · "
            "[Request ZDR](https://www.anthropic.com/contact-sales)"
        )

    st.divider()

    uploaded = st.file_uploader("Upload manuscript (PDF)", type=["pdf"])
    if uploaded:
        if uploaded.name != st.session_state.pdf_name:
            with st.spinner("Encoding PDF in memory…"):
                b64, txt, sha = encode_pdf(uploaded)
            st.session_state.pdf_base64   = b64
            st.session_state.pdf_text     = txt
            st.session_state.pdf_hash     = sha
            st.session_state.pdf_name     = uploaded.name
            st.session_state.report       = None
            st.session_state.raw_report   = ""
            st.session_state.chat_history = []
            st.session_state.upload_count += 1
        st.success(f"✅ {uploaded.name}")
        st.caption(
            f"{len(st.session_state.pdf_text):,} chars · "
            f"SHA-256: {st.session_state.pdf_hash[:12]}…"
        )

    st.divider()

    journal = st.selectbox("Target journal", JOURNALS)

    st.markdown("**Review criteria**")
    selected_criteria = [
        key for key, label in REVIEW_CRITERIA.items()
        if st.checkbox(label, value=True, key=f"cb_{key}")
    ]

    st.divider()

    can_analyze = bool(st.session_state.pdf_base64) and len(selected_criteria) > 0
    if st.button("🚀 Run Full Analysis", disabled=not can_analyze, use_container_width=True):
        st.session_state.report       = None
        st.session_state.raw_report   = ""
        st.session_state.chat_history = []
        st.session_state["_trigger_analysis"] = True

    st.divider()

    if st.button("🗑️ Clear Session & Delete All Data", use_container_width=True):
        clear_session_data()
        st.success("Session cleared. All document data removed from memory.")
        st.rerun()

    st.caption(
        "⚠️ Closing this tab also clears all data. "
        "No manuscript content is retained between sessions."
    )

# ─── ANALYSIS ─────────────────────────────────────────────────────────────────
if st.session_state.get("_trigger_analysis"):
    st.session_state["_trigger_analysis"] = False

    system = build_system_prompt(journal)
    prompt = build_review_prompt(selected_criteria, journal)

    phases = [
        "Phase 1 — Deep document read & structure audit",
        "Phase 2 — Methodology & criteria assessment",
        "Phase 3 — Citation audit & gap analysis",
        "Phase 4 — Generating structured review report",
    ]

    progress = st.progress(0)
    status   = st.status("Running analysis…", expanded=True)
    raw        = None
    model_used = PRIMARY_MODEL

    for i, phase in enumerate(phases):
        status.write(f"⚙️ {phase}")
        progress.progress((i + 1) / len(phases))

    try:
        status.write(f"🧠 Sending to {PRIMARY_MODEL} with native PDF support…")
        raw        = call_api_with_pdf(system, prompt, PRIMARY_MODEL)
        model_used = PRIMARY_MODEL
    except NotFoundError:
        status.write(f"⚠️ {PRIMARY_MODEL} unavailable — falling back to {FALLBACK_MODEL}…")
        try:
            raw        = call_api_with_pdf(system, prompt, FALLBACK_MODEL)
            model_used = FALLBACK_MODEL
        except Exception:
            status.write("⚠️ Native PDF failed — using extracted text…")
            raw        = call_api_with_text(system, prompt, FALLBACK_MODEL)
            model_used = FALLBACK_MODEL + " (text mode)"
    except Exception as e:
        status.write(f"⚠️ PDF mode error ({e}) — retrying with extracted text…")
        try:
            raw        = call_api_with_text(system, prompt, PRIMARY_MODEL)
            model_used = PRIMARY_MODEL + " (text mode)"
        except Exception as e2:
            status.update(label=f"Error: {e2}", state="error")
            st.stop()

    progress.progress(1.0)
    parsed = parse_report(raw)
    st.session_state.report     = parsed
    st.session_state.raw_report = raw
    st.session_state.model_used = model_used

    st.session_state.chat_history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": st.session_state.pdf_base64,
                    },
                },
                {"type": "text", "text": "This is the manuscript we just reviewed."},
            ],
        },
        {
            "role": "assistant",
            "content": f"I have completed a full peer review. Structured analysis:\n{raw}",
        },
    ]

    status.update(label="Analysis complete ✓", state="complete", expanded=False)
    st.rerun()

# ─── IDLE STATE ───────────────────────────────────────────────────────────────
if not st.session_state.report and not st.session_state.raw_report:
    st.markdown(
        """
        <div style="text-align:center;padding:4rem 2rem;">
          <h2 style="font-size:2rem;">🎓 HPE Manuscript Reviewer</h2>
          <p style="color:#666;max-width:500px;margin:1rem auto;line-height:1.7">
            Upload a manuscript PDF in the sidebar, choose your target journal and
            review criteria, then click <strong>Run Full Analysis</strong>.
          </p>
          <div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:1.5rem">
            <span style="background:#e8f4f0;color:#1d6b52;padding:5px 14px;border-radius:20px;font-size:0.85rem">Multi-phase analysis</span>
            <span style="background:#e8f4f0;color:#1d6b52;padding:5px 14px;border-radius:20px;font-size:0.85rem">Native PDF understanding</span>
            <span style="background:#e8f4f0;color:#1d6b52;padding:5px 14px;border-radius:20px;font-size:0.85rem">CONSORT / SRQR / COREQ</span>
            <span style="background:#e8f4f0;color:#1d6b52;padding:5px 14px;border-radius:20px;font-size:0.85rem">Kirkpatrick framework</span>
            <span style="background:#e8f4f0;color:#1d6b52;padding:5px 14px;border-radius:20px;font-size:0.85rem">Citation audit</span>
            <span style="background:#e8f4f0;color:#1d6b52;padding:5px 14px;border-radius:20px;font-size:0.85rem">Interactive Q&A</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ─── MAIN DISPLAY ─────────────────────────────────────────────────────────────
report = st.session_state.report
raw    = st.session_state.raw_report

st.caption(f"Generated with **{st.session_state.model_used}**")

tab_report, tab_chat = st.tabs(["📝 Review Report", "💬 Editor Chat"])

# ─── REPORT TAB ───────────────────────────────────────────────────────────────
with tab_report:
    if report is None:
        st.warning("Could not parse structured JSON — showing raw report.")
        st.text_area("Raw report", raw, height=600)
    else:
        verdict = report.get("verdict", "Unknown")
        score   = report.get("overall_score", "—")

        col_v, col_s, col_dl = st.columns([3, 1, 1])
        with col_v:
            st.markdown(render_verdict_badge(verdict), unsafe_allow_html=True)
        with col_s:
            st.metric("Overall score", f"{score}/100")
        with col_dl:
            docx_bytes = create_docx(report, raw)
            st.download_button(
                "⬇️ Download .docx",
                data=docx_bytes,
                file_name="HPE_Review_Report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        st.markdown(f"> {report.get('executive_summary','')}")
        st.divider()

        scores = report.get("scores", {})
        if scores:
            cols = st.columns(len(scores))
            for col, (k, v) in zip(cols, scores.items()):
                col.metric(k.capitalize(), f"{v}/10")

        kp = report.get("kirkpatrick_level", {})
        if kp:
            st.info(f"🎯 **Kirkpatrick Level {kp.get('level','?')}** — {kp.get('justification','')}")

        st.divider()

        with st.expander("🧵 Golden Thread Analysis", expanded=True):
            st.write(report.get("golden_thread", "—"))

        strengths = report.get("strengths", [])
        if strengths:
            with st.expander(f"✅ Strengths ({len(strengths)})", expanded=True):
                for s in strengths:
                    st.markdown(f"- {s}")

        weaknesses = report.get("weaknesses", [])
        if weaknesses:
            majors = [w for w in weaknesses if w.get("severity") == "major"]
            minors = [w for w in weaknesses if w.get("severity") != "major"]
            with st.expander(f"⚠️ Weaknesses — {len(majors)} major, {len(minors)} minor", expanded=True):
                for w in weaknesses:
                    sev    = w.get("severity", "minor")
                    colour = "🔴" if sev == "major" else "🟡"
                    st.markdown(
                        f"{colour} **[{sev.upper()} — {w.get('section','')}]** {w.get('issue','')}"
                    )
                    if w.get("suggestion"):
                        st.caption(f"→ {w['suggestion']}")

        sc = report.get("section_comments", {})
        if sc:
            with st.expander("📝 Section-by-Section Comments"):
                for section, comment in sc.items():
                    st.markdown(f"**{section.capitalize()}**")
                    st.write(comment)
                    st.divider()

        ca = report.get("citation_audit", {})
        if ca:
            with st.expander("📚 Citation Audit"):
                missing = ca.get("missing_key_references", [])
                if missing:
                    st.markdown("**Missing key references:**")
                    for ref in missing:
                        st.markdown(f"- {ref}")
                outdated = ca.get("potentially_outdated", [])
                if outdated:
                    st.markdown("**Potentially outdated:**")
                    for ref in outdated:
                        st.markdown(f"- {ref}")
                st.markdown(f"**Mismatches:** {ca.get('mismatches','None identified')}")

        recs = report.get("actionable_recommendations", [])
        if recs:
            with st.expander(f"✅ Actionable Recommendations ({len(recs)})", expanded=True):
                for i, rec in enumerate(recs, 1):
                    st.markdown(f"**{i}.** {rec}")

        editor_note = report.get("editor_note", "")
        if editor_note:
            with st.expander("🔒 Confidential Note to Editor"):
                st.info(editor_note)

# ─── CHAT TAB ─────────────────────────────────────────────────────────────────
with tab_chat:
    st.caption("Ask questions about the review or the manuscript. The full PDF is in context.")

    quick_prompts = [
        "Expand on the methodology critique",
        "Which specific citations are missing and why?",
        "How can the Discussion section be strengthened?",
        "Explain the golden thread score in detail",
        "What would it take to reach Kirkpatrick Level 3 or 4?",
        "Suggest a revised abstract",
    ]
    cols = st.columns(3)
    for i, qp in enumerate(quick_prompts):
        if cols[i % 3].button(qp, key=f"qp_{i}", use_container_width=True):
            st.session_state._pending_chat = qp

    st.divider()

    display_history = st.session_state.chat_history[2:]
    for msg in display_history:
        role    = msg["role"]
        content = msg["content"] if isinstance(msg["content"], str) else str(msg["content"])
        with st.chat_message(role):
            st.markdown(content)

    pending    = st.session_state.pop("_pending_chat", None)
    user_input = st.chat_input("Ask about the review or manuscript…") or pending

    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    response = client.messages.create(
                        model=FALLBACK_MODEL,
                        max_tokens=2048,
                        system=(
                            "You are a Senior HPE Journal Editor who just completed a peer review. "
                            "Answer questions about the manuscript and the review precisely. "
                            "Quote specific manuscript passages when relevant. "
                            "Be constructive and suggest concrete improvements."
                        ),
                        messages=st.session_state.chat_history,
                    )
                    reply = response.content[0].text
                except Exception as e:
                    reply = f"Error: {e}"

            st.markdown(reply)
            st.session_state.chat_history.append({"role": "assistant", "content": reply})
