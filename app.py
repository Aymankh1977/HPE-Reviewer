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

try:
    from duckduckgo_search import DDGS
    DDG_AVAILABLE = True
except ImportError:
    DDG_AVAILABLE = False

# ─── CONFIG ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DentEdTech™ | HPE Expert Reviewer",
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

# ─── JOURNALS ─────────────────────────────────────────────────────────────────
JOURNALS = [
    # General HPE
    "Medical Teacher",
    "BMC Medical Education",
    "Academic Medicine",
    "Medical Education",
    "JGME – Journal of Graduate Medical Education",
    "Teaching and Learning in Medicine",
    "Advances in Health Sciences Education",
    # Dental Education
    "Journal of Dental Education (JDE)",
    "European Journal of Dental Education (EJDE)",
    "Journal of Dental Research (JDR)",
    "Journal of Dentistry",
    "British Dental Journal (BDJ)",
    "European Journal of Oral Sciences",
    "Journal of Dental Sciences",
    "International Journal of Dental Education",
    "Dental Education Today (ADEE)",
    "Journal of Dental Hygiene Education",
]

# ─── REVIEW CRITERIA ──────────────────────────────────────────────────────────
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
    "consent_given":     False,
    "pdf_base64":        None,
    "pdf_name":          "",
    "pdf_hash":          "",
    "pdf_text":          "",
    "report":            None,
    "raw_report":        "",
    "chat_history":      [],
    "model_used":        "",
    "session_start":     None,
    "upload_count":      0,
    "similarity_report": None,
    "raw_similarity":    "",
    "search_results":    [],
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
          <h2 style="margin-top:0">🎓 DentEdTech™</h2>
          <h4 style="color:#1a3a4a;margin-top:0">HPE Expert Reviewer</h4>
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
    sensitive_keys = [
        "pdf_base64", "pdf_name", "pdf_hash", "pdf_text",
        "report", "raw_report", "chat_history", "model_used",
        "similarity_report", "raw_similarity", "search_results",
    ]
    for k in sensitive_keys:
        st.session_state[k] = defaults[k]
    st.session_state.upload_count = 0


def extract_search_queries(pdf_text: str) -> list[str]:
    """Ask Claude to extract 5 key phrases most likely to be similar to published work."""
    prompt = (
        "Read this manuscript excerpt and extract exactly 5 short search queries "
        "(4-8 words each) that represent the most distinctive claims, methods, or "
        "findings. These will be used to search for similar published papers. "
        "Return ONLY a JSON array of 5 strings, no other text.\n\n"
        f"MANUSCRIPT EXCERPT:\n{pdf_text[:8000]}"
    )
    try:
        response = client.messages.create(
            model=CHAT_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        start = raw.index("["); end = raw.rindex("]") + 1
        return json.loads(raw[start:end])
    except Exception:
        # Fallback: extract first sentence of abstract as query
        lines = [l.strip() for l in pdf_text.split("\n") if len(l.strip()) > 40]
        return [lines[0][:80]] if lines else ["dental education quality assurance AI"]


def search_web(queries: list[str]) -> list[dict]:
    """Search DuckDuckGo for each query and return results."""
    if not DDG_AVAILABLE:
        return []
    all_results = []
    seen_urls = set()
    try:
        with DDGS() as ddgs:
            for query in queries:
                try:
                    results = list(ddgs.text(
                        f"{query} site:pubmed.ncbi.nlm.nih.gov OR site:scholar.google.com "
                        f"OR site:researchgate.net OR site:tandfonline.com OR site:wiley.com "
                        f"OR site:springer.com OR site:sciencedirect.com",
                        max_results=3,
                    ))
                    for r in results:
                        url = r.get("href", "")
                        if url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append({
                                "title": r.get("title", ""),
                                "url":   url,
                                "body":  r.get("body", ""),
                                "query": query,
                            })
                except Exception:
                    continue
    except Exception:
        pass
    return all_results[:12]  # cap at 12 results total


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
      "issue": "<specific issue quoting the manuscript text>",
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
  "golden_thread": "<Paragraph assessing RQ to methodology to results to conclusion coherence>",
  "kirkpatrick_level": {{
    "level": <1|2|3|4>,
    "justification": "<why this level>"
  }},
  "citation_audit": {{
    "missing_key_references": ["<Author Year — why relevant>"],
    "potentially_outdated": ["<citation — reason>"],
    "mismatches": "<in-text vs reference list issues, or None identified>"
  }},
  "actionable_recommendations": ["<Numbered, specific action the authors must take>"],
  "editor_note": "<Confidential note to the editor — not shared with authors>"
}}"""


def build_similarity_prompt(search_results: list[dict]) -> str:
    search_block = ""
    if search_results:
        search_block = "\n\nSIMILAR PUBLISHED PAPERS FOUND ONLINE:\n"
        for i, r in enumerate(search_results, 1):
            search_block += (
                f"\n[{i}] Title: {r['title']}\n"
                f"    URL: {r['url']}\n"
                f"    Summary: {r['body'][:300]}\n"
            )

    return f"""You are an academic integrity and publication similarity specialist.
Analyse this manuscript for originality and similarity risks.

1. SIMILARITY TO PUBLISHED LITERATURE:
   Using the search results below, assess how closely this manuscript's topic,
   methodology, or findings overlap with already-published papers.
   For each similar paper found, explain what overlaps and what the authors should do.

2. INTERNAL ORIGINALITY AUDIT:
   Identify passages that are:
   - Boilerplate or copied from standard sources (definitions, guideline text, protocols)
   - Factual claims with no citation
   - Sections with sudden style changes suggesting imported text
   - Passages repeated between sections (abstract, introduction, discussion, conclusion)

3. METHODS SECTION RISK:
   Assess whether the methods section reads as original or copied from guidelines/protocols.

4. OVERALL SIMILARITY RISK:
   Give an estimated risk level and percentage with specific rewrite advice.
{search_block}

Return ONLY a valid JSON object — no markdown, no preamble:

{{
  "overall_risk_level": "Low | Moderate | High | Very High",
  "estimated_similarity_risk_percent": <integer 0-100>,
  "disclaimer": "This is an AI-based originality risk assessment. It searches open-access content only and is not equivalent to Turnitin or iThenticate. Always use your institution's official similarity checker before submission.",
  "similar_publications": [
    {{
      "title": "<paper title>",
      "url": "<paper url>",
      "overlap_description": "<what specifically overlaps with this manuscript>",
      "overlap_type": "topic | methodology | findings | framing | significant overlap",
      "risk_level": "Low | Moderate | High",
      "recommendation": "<what authors should do to differentiate>"
    }}
  ],
  "boilerplate_sections": [
    {{
      "section": "<where in the paper>",
      "passage": "<quoted text from manuscript>",
      "risk": "<why this is high risk>",
      "suggestion": "<how to rewrite>"
    }}
  ],
  "citation_free_claims": [
    {{
      "passage": "<quoted text>",
      "risk": "<what claim needs a citation>",
      "suggestion": "<what to cite>"
    }}
  ],
  "internal_repetition": [
    {{
      "passage": "<quoted text>",
      "appears_in": ["<section 1>", "<section 2>"]
    }}
  ],
  "methods_risk": "<assessment of the methods section originality>",
  "priority_rewrites": ["<specific numbered rewrite instruction>"],
  "submission_readiness": "<overall verdict and advice on similarity risk>"
}}"""


def call_api_with_pdf(system: str, user_prompt: str, model: str, max_tok: int = 4096) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=max_tok,
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


def call_api_with_text(system: str, user_prompt: str, model: str, max_tok: int = 4096) -> str:
    text = st.session_state.pdf_text[:100_000]
    full_prompt = f"MANUSCRIPT TEXT:\n{text}\n\n{user_prompt}"
    response = client.messages.create(
        model=model,
        max_tokens=max_tok,
        system=system,
        messages=[{"role": "user", "content": full_prompt}],
    )
    return response.content[0].text


def parse_json(raw: str) -> dict | None:
    """Parse JSON robustly — handles markdown fences, preamble, and nested braces."""
    if not raw:
        return None
    cleaned = raw.strip()
    # Strip markdown code fences
    if "```" in cleaned:
        parts = cleaned.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                cleaned = part
                break
    # Find outermost JSON object using brace matching
    try:
        start = cleaned.index("{")
        depth = 0
        end = start
        for i, ch in enumerate(cleaned[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        return json.loads(cleaned[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


def create_docx(report: dict | None, raw: str) -> bytes:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    heading = doc.add_heading("DentEdTech™ — HPE Peer Review Report", 0)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer      = doc.sections[0].footer
    footer_para = footer.paragraphs[0]
    footer_para.text = (
        "CONFIDENTIAL — Generated by DentEdTech™ HPE Expert Reviewer. "
        "Powered by Anthropic API. DentEdTech™ — Not for redistribution."
    )
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if report is None:
        doc.add_paragraph(raw)
    else:
        def h2(text):
            doc.add_heading(text, level=2)
        verdict = report.get("verdict", "—")
        score   = report.get("overall_score", "—")
        p   = doc.add_paragraph()
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
            doc.add_paragraph(
                f"[{sev} — {w.get('section','')}] {w.get('issue','')}\n→ {w.get('suggestion','')}",
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
    if "reject" in vl:                                                key = "reject"
    elif "major" in vl:                                               key = "major"
    elif "accept" in vl and "minor" not in vl and "major" not in vl: key = "accept"
    bg, fg = colours[key]
    return (
        f'<span style="background:{bg};color:{fg};padding:4px 14px;'
        f'border-radius:20px;font-weight:600;font-size:0.9rem;">{verdict}</span>'
    )


def render_risk_badge(risk: str) -> str:
    colours = {
        "low":       ("#d4edda", "#155724"),
        "moderate":  ("#fff3cd", "#856404"),
        "high":      ("#f8d7da", "#721c24"),
        "very high": ("#f5c6cb", "#491217"),
    }
    key = risk.lower().strip()
    bg, fg = colours.get(key, ("#e2e3e5", "#383d41"))
    return (
        f'<span style="background:{bg};color:{fg};padding:4px 14px;'
        f'border-radius:20px;font-weight:600;font-size:0.9rem;">Risk: {risk}</span>'
    )


def render_overlap_badge(level: str) -> str:
    colours = {
        "low":      ("#d4edda", "#155724"),
        "moderate": ("#fff3cd", "#856404"),
        "high":     ("#f8d7da", "#721c24"),
    }
    key = level.lower().strip()
    bg, fg = colours.get(key, ("#e2e3e5", "#383d41"))
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 10px;'
        f'border-radius:12px;font-size:0.8rem;font-weight:600;">{level}</span>'
    )


# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎓 DentEdTech™")
    st.subheader("HPE Expert Reviewer")
    st.caption("Powered by Claude · Multi-phase critical analysis")

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
        if uploaded.name != st.session_state.pdf_name or (
            uploaded.name == st.session_state.pdf_name and not st.session_state.pdf_base64
        ):
            with st.spinner("Encoding PDF in memory…"):
                b64, txt, sha = encode_pdf(uploaded)
            # Only reset if file actually changed (compare hash)
            if sha != st.session_state.pdf_hash:
                st.session_state.pdf_base64        = b64
                st.session_state.pdf_text          = txt
                st.session_state.pdf_hash          = sha
                st.session_state.pdf_name          = uploaded.name
                st.session_state.report            = None
                st.session_state.raw_report        = ""
                st.session_state.chat_history      = []
                st.session_state.similarity_report = None
                st.session_state.raw_similarity    = ""
                st.session_state.search_results    = []
                st.session_state.upload_count     += 1
                st.success(f"✅ New file loaded: {uploaded.name}")
            else:
                st.success(f"✅ {uploaded.name} (unchanged)")
        else:
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
    parsed = parse_json(raw)
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
          <h2 style="font-size:2rem;">🎓 DentEdTech™</h2>
          <h3 style="font-size:1.3rem;color:#555;margin-top:0">HPE Manuscript Reviewer</h3>
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
            <span style="background:#e8f4f0;color:#1d6b52;padding:5px 14px;border-radius:20px;font-size:0.85rem">Web similarity search</span>
            <span style="background:#e8f4f0;color:#1d6b52;padding:5px 14px;border-radius:20px;font-size:0.85rem">Interactive Q&amp;A</span>
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

tab_report, tab_similarity, tab_chat = st.tabs([
    "📝 Review Report",
    "🔍 Similarity & Originality Audit",
    "💬 Editor Chat",
])

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
                file_name="DentEdTech_Review_Report.docx",
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

# ─── SIMILARITY TAB ───────────────────────────────────────────────────────────
with tab_similarity:
    st.info(
        "⚠️ **Important disclaimer:** This tool searches open-access content online "
        "(PubMed, ResearchGate, publisher sites) and analyses your manuscript internally. "
        "It is **not** equivalent to Turnitin or iThenticate. Always run your final manuscript "
        "through your institution's official similarity checker before submission."
    )

    if not DDG_AVAILABLE:
        st.warning(
            "Web search is unavailable — `duckduckgo-search` is not installed. "
            "Add `duckduckgo-search` to your `requirements.txt` to enable online search. "
            "Internal originality audit will still run."
        )

    # Show current file being audited
    if st.session_state.pdf_name:
        col_f, col_clr = st.columns([4, 1])
        with col_f:
            st.caption(
                f"📄 Current manuscript: **{st.session_state.pdf_name}** "
                f"· SHA-256: `{st.session_state.pdf_hash[:16]}…`"
            )
        with col_clr:
            if st.button("🔄 Clear audit", help="Force clear cached results and re-run"):
                st.session_state.similarity_report = None
                st.session_state.raw_similarity    = ""
                st.session_state.search_results    = []
                st.rerun()

    if st.button(
        "🔍 Run Similarity & Originality Audit",
        disabled=not bool(st.session_state.pdf_base64),
        use_container_width=False,
    ):
        st.session_state.similarity_report = None
        st.session_state.raw_similarity    = ""
        st.session_state.search_results    = []

        with st.status("Running similarity audit…", expanded=True) as sim_status:

            # Step 1 — Extract search queries
            sim_status.write("🔎 Step 1 — Extracting key phrases from manuscript…")
            queries = extract_search_queries(st.session_state.pdf_text)
            sim_status.write(f"   Found {len(queries)} search queries")

            # Step 2 — Web search
            if DDG_AVAILABLE:
                sim_status.write("🌐 Step 2 — Searching open-access publications online…")
                search_results = search_web(queries)
                st.session_state.search_results = search_results
                sim_status.write(f"   Found {len(search_results)} potentially similar papers")
            else:
                search_results = []
                sim_status.write("⚠️ Step 2 — Web search skipped (duckduckgo-search not installed)")

            # Step 3 — AI analysis
            sim_status.write("🧠 Step 3 — Analysing manuscript originality with AI…")
            sim_prompt = build_similarity_prompt(search_results)
            sim_system = (
                "You are an academic integrity and publication similarity specialist. "
                "You analyse manuscripts for similarity risks, boilerplate text, "
                "paraphrase patterns, and overlap with published literature. "
                "You are precise, quote exact passages, and never fabricate."
            )

            sim_raw = None
            try:
                sim_raw = call_api_with_pdf(sim_system, sim_prompt, FALLBACK_MODEL, max_tok=6000)
            except Exception as e:
                sim_status.write(f"⚠️ PDF mode failed ({e}) — using text mode…")
                try:
                    sim_raw = call_api_with_text(sim_system, sim_prompt, FALLBACK_MODEL, max_tok=6000)
                except Exception as e2:
                    sim_status.update(label=f"Error: {e2}", state="error")
                    st.stop()

            parsed_sim = parse_json(sim_raw)
            st.session_state.similarity_report = parsed_sim
            st.session_state.raw_similarity    = sim_raw
            sim_status.update(label="Similarity audit complete ✓", state="complete", expanded=False)
        st.rerun()

    # ── Display results ────────────────────────────────────────────────────────
    sim = st.session_state.similarity_report

    if sim is None and st.session_state.raw_similarity:
        # Attempt a second parse in case the first failed
        sim = parse_json(st.session_state.raw_similarity)
        if sim:
            st.session_state.similarity_report = sim
        else:
            st.warning(
                "The AI returned a response that could not be fully parsed. "
                "Showing key sections below."
            )
            raw_sim = st.session_state.raw_similarity
            # Try to display meaningfully even without full parse
            st.markdown("**Raw AI Response:**")
            # Remove JSON fences for display
            display_text = raw_sim.replace("```json", "").replace("```", "").strip()
            try:
                # Try to pretty-print as JSON
                pretty = json.dumps(json.loads(
                    display_text[display_text.index("{"):display_text.rindex("}")+1]
                ), indent=2)
                st.code(pretty, language="json")
            except Exception:
                st.text_area("Response", display_text, height=400)

    elif sim:
        risk = sim.get("overall_risk_level", "Unknown")
        est  = sim.get("estimated_similarity_risk_percent", "—")

        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(render_risk_badge(risk), unsafe_allow_html=True)
        with col2:
            st.metric(
                "Estimated risk", f"~{est}%",
                help="AI estimate based on open-access search — not equivalent to Turnitin",
            )

        st.caption(sim.get("disclaimer", ""))
        st.markdown(f"**Submission readiness:** {sim.get('submission_readiness','—')}")
        st.divider()

        # ── Similar publications found online ──────────────────────────────────
        pubs = sim.get("similar_publications", [])
        if pubs:
            with st.expander(f"🌐 Similar Publications Found Online ({len(pubs)})", expanded=True):
                for p in pubs:
                    rl = p.get("risk_level", "")
                    st.markdown(
                        f"**{p.get('title','')}** "
                        f"{render_overlap_badge(rl)}",
                        unsafe_allow_html=True,
                    )
                    if p.get("url"):
                        st.markdown(f"🔗 [{p['url']}]({p['url']})")
                    st.markdown(f"**Overlap:** {p.get('overlap_description','')}")
                    st.markdown(f"**Overlap type:** `{p.get('overlap_type','')}`")
                    if p.get("recommendation"):
                        st.success(f"✏️ {p['recommendation']}")
                    st.divider()
        else:
            with st.expander("🌐 Similar Publications Found Online", expanded=False):
                st.success("✅ No significantly similar papers identified in open-access search.")

        # ── Search queries used ────────────────────────────────────────────────
        if st.session_state.search_results:
            with st.expander(f"🔎 Raw Search Results ({len(st.session_state.search_results)} papers found)", expanded=False):
                st.caption("These are the papers retrieved from the web search before AI analysis.")
                for r in st.session_state.search_results:
                    st.markdown(f"**{r['title']}**")
                    st.caption(f"Query: `{r['query']}` · URL: {r['url']}")
                    st.write(r["body"][:200] + "…")
                    st.divider()

        # ── Boilerplate ────────────────────────────────────────────────────────
        boiler = sim.get("boilerplate_sections", [])
        if boiler:
            with st.expander(f"📋 Boilerplate Sections Detected ({len(boiler)})", expanded=True):
                for item in boiler:
                    st.markdown(f"**Section:** {item.get('section','')}")
                    st.warning(f"🔴 **High-risk passage:**\n> {item.get('passage','')}")
                    st.caption(f"Risk: {item.get('risk','')}")
                    st.success(f"✏️ Suggestion: {item.get('suggestion','')}")
                    st.divider()
        else:
            with st.expander("📋 Boilerplate Sections", expanded=False):
                st.success("✅ No significant boilerplate detected.")

        # ── Citation-free claims ───────────────────────────────────────────────
        claims = sim.get("citation_free_claims", [])
        if claims:
            with st.expander(f"📎 Citation-Free Factual Claims ({len(claims)})", expanded=True):
                for item in claims:
                    st.warning(f"🟡 **Uncited claim:**\n> {item.get('passage','')}")
                    st.caption(f"Risk: {item.get('risk','')}")
                    st.success(f"✏️ Suggestion: {item.get('suggestion','')}")
                    st.divider()
        else:
            with st.expander("📎 Citation-Free Claims", expanded=False):
                st.success("✅ No significant uncited claims detected.")

        # ── Internal repetition ────────────────────────────────────────────────
        repeats = sim.get("internal_repetition", [])
        if repeats:
            with st.expander(f"🔁 Internal Repetition ({len(repeats)})", expanded=True):
                for item in repeats:
                    st.warning(f"🟡 **Repeated passage:**\n> {item.get('passage','')}")
                    st.caption(f"Appears in: {', '.join(item.get('appears_in', []))}")
                    st.divider()
        else:
            with st.expander("🔁 Internal Repetition", expanded=False):
                st.success("✅ No significant internal repetition detected.")

        # ── Methods risk ───────────────────────────────────────────────────────
        methods_risk = sim.get("methods_risk", "")
        if methods_risk:
            with st.expander("🔬 Methods Section Originality", expanded=True):
                st.write(methods_risk)

        # ── Priority rewrites ──────────────────────────────────────────────────
        rewrites = sim.get("priority_rewrites", [])
        if rewrites:
            with st.expander(f"✏️ Priority Rewrites ({len(rewrites)})", expanded=True):
                for i, rw in enumerate(rewrites, 1):
                    st.markdown(f"**{i}.** {rw}")

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
