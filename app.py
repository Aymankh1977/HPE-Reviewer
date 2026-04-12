"""
DentEdTech Evidence Engine
An educational AI platform for medicine, dentistry, and pharmacology students
at Manchester University. Built on the REAL-AI framework principles.

© DentEdTech - All Rights Reserved
"""

import streamlit as st
import anthropic
import json
import re
from datetime import datetime

# ─── Page Config ───
st.set_page_config(
    page_title="DentEdTech Evidence Engine",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');

/* Root variables */
:root {
    --primary: #1B4D3E;
    --primary-light: #2D7A5F;
    --accent: #D4A853;
    --accent-light: #E8C97A;
    --bg-dark: #0F1A16;
    --bg-card: #162520;
    --bg-card-hover: #1C3029;
    --text-primary: #E8EDE9;
    --text-secondary: #9BAFA3;
    --text-muted: #6B8577;
    --border: #2D4A3E;
    --danger: #C44B4B;
    --warning: #D4A853;
    --success: #4CAF7D;
}

/* Global overrides */
.stApp {
    background-color: var(--bg-dark) !important;
    color: var(--text-primary) !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* Hide Streamlit branding */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Main header */
.main-header {
    text-align: center;
    padding: 2rem 1rem 1.5rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 2rem;
}
.main-header h1 {
    font-family: 'DM Serif Display', serif !important;
    font-size: 2.4rem !important;
    color: var(--text-primary) !important;
    margin: 0 !important;
    letter-spacing: -0.02em;
}
.main-header .tagline {
    font-size: 0.95rem;
    color: var(--text-secondary);
    margin-top: 0.3rem;
    font-style: italic;
}
.brand-accent {
    color: var(--accent) !important;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background-color: var(--bg-card) !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown li,
section[data-testid="stSidebar"] label {
    color: var(--text-secondary) !important;
    font-family: 'DM Sans', sans-serif !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: var(--text-primary) !important;
    font-family: 'DM Serif Display', serif !important;
}

/* Mode selector cards */
.mode-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    transition: all 0.3s ease;
}
.mode-card:hover {
    border-color: var(--accent);
    background: var(--bg-card-hover);
}
.mode-card h3 {
    font-family: 'DM Serif Display', serif !important;
    color: var(--text-primary) !important;
    margin-top: 0 !important;
    font-size: 1.2rem !important;
}
.mode-card p {
    color: var(--text-secondary) !important;
    font-size: 0.88rem !important;
    line-height: 1.5 !important;
}

/* REAL-AI pillar badges */
.pillar-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-right: 6px;
    margin-bottom: 4px;
}
.pillar-r { background: rgba(76, 175, 125, 0.15); color: #4CAF7D; border: 1px solid rgba(76, 175, 125, 0.3); }
.pillar-e { background: rgba(212, 168, 83, 0.15); color: #D4A853; border: 1px solid rgba(212, 168, 83, 0.3); }
.pillar-a { background: rgba(100, 149, 237, 0.15); color: #6495ED; border: 1px solid rgba(100, 149, 237, 0.3); }
.pillar-l { background: rgba(196, 75, 75, 0.15); color: #E07070; border: 1px solid rgba(196, 75, 75, 0.3); }

/* Chat message styling */
.chat-msg {
    padding: 1.2rem 1.5rem;
    border-radius: 12px;
    margin-bottom: 1rem;
    line-height: 1.7;
    font-size: 0.92rem;
}
.chat-msg-user {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
}
.chat-msg-assistant {
    background: rgba(27, 77, 62, 0.15);
    border: 1px solid rgba(45, 122, 95, 0.25);
    border-left: 3px solid var(--primary-light);
}
.chat-msg-system {
    background: rgba(212, 168, 83, 0.08);
    border: 1px solid rgba(212, 168, 83, 0.2);
    border-left: 3px solid var(--accent);
    font-style: italic;
}

/* EBL phase indicator */
.ebl-phase {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1.5rem;
}
.ebl-phase-title {
    font-family: 'DM Serif Display', serif !important;
    font-size: 1.1rem !important;
    color: var(--accent) !important;
    margin-bottom: 0.5rem !important;
}
.ebl-phase-desc {
    color: var(--text-secondary) !important;
    font-size: 0.85rem !important;
    line-height: 1.5 !important;
}

/* Phase stepper */
.phase-stepper {
    display: flex;
    justify-content: space-between;
    margin-bottom: 1.5rem;
    padding: 0.8rem 0;
}
.phase-step {
    flex: 1;
    text-align: center;
    position: relative;
    padding: 0 0.5rem;
}
.phase-dot {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 700;
    margin-bottom: 0.4rem;
    transition: all 0.3s ease;
}
.phase-dot-active {
    background: var(--accent);
    color: var(--bg-dark);
}
.phase-dot-done {
    background: var(--success);
    color: var(--bg-dark);
}
.phase-dot-pending {
    background: var(--bg-card);
    color: var(--text-muted);
    border: 1px solid var(--border);
}
.phase-label {
    font-size: 0.7rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.phase-label-active {
    color: var(--accent) !important;
    font-weight: 600;
}

/* Reflection prompt box */
.reflection-box {
    background: rgba(212, 168, 83, 0.06);
    border: 1px dashed rgba(212, 168, 83, 0.35);
    border-radius: 10px;
    padding: 1.2rem 1.5rem;
    margin: 1rem 0;
}
.reflection-box h4 {
    color: var(--accent) !important;
    font-family: 'DM Serif Display', serif !important;
    font-size: 0.95rem !important;
    margin-bottom: 0.5rem !important;
}
.reflection-box p {
    color: var(--text-secondary) !important;
    font-size: 0.85rem !important;
}

/* Source cards */
.source-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.6rem;
    font-size: 0.82rem;
    transition: border-color 0.2s ease;
}
.source-card:hover {
    border-color: var(--primary-light);
}
.source-type {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 600;
    margin-bottom: 0.3rem;
}
.source-journal { color: var(--success); }
.source-university { color: #6495ED; }
.source-video { color: var(--danger); }

/* Limitation notice */
.limitation-notice {
    background: rgba(196, 75, 75, 0.08);
    border: 1px solid rgba(196, 75, 75, 0.2);
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin-top: 1rem;
    font-size: 0.78rem;
    color: var(--text-muted);
}
.limitation-notice strong {
    color: var(--danger);
}

/* Input styling */
.stTextArea textarea, .stTextInput input {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
    border-radius: 10px !important;
    font-family: 'DM Sans', sans-serif !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 1px var(--accent) !important;
}

/* Button styling */
.stButton > button {
    background-color: var(--primary) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--primary-light) !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    padding: 0.5rem 1.5rem !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background-color: var(--primary-light) !important;
    border-color: var(--accent) !important;
}

/* Selectbox */
.stSelectbox > div > div {
    background-color: var(--bg-card) !important;
    border-color: var(--border) !important;
    color: var(--text-primary) !important;
}

/* Radio buttons */
.stRadio label {
    color: var(--text-secondary) !important;
}

/* Expander */
.streamlit-expanderHeader {
    background-color: var(--bg-card) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}

/* Divider */
.section-divider {
    border: none;
    border-top: 1px solid var(--border);
    margin: 1.5rem 0;
}

/* Footer */
.app-footer {
    text-align: center;
    padding: 1.5rem;
    border-top: 1px solid var(--border);
    margin-top: 2rem;
    color: var(--text-muted);
    font-size: 0.75rem;
}
</style>
""", unsafe_allow_html=True)


# ─── System Prompts ───

EVIDENCE_SYSTEM_PROMPT = """You are the DentEdTech Evidence Engine, an educational AI assistant for medicine, dentistry, and pharmacology students at the University of Manchester. You operate under the REAL-AI framework principles.

## YOUR STRICT SOURCE CONSTRAINTS
You may ONLY provide information from these source types:
1. **Scientific journals** (PubMed-indexed, peer-reviewed): e.g., Journal of Dental Research, The Lancet, BMJ, NEJM, Journal of Dental Education, European Journal of Dental Education, British Dental Journal, Journal of Clinical Pharmacology, etc.
2. **University websites** (.ac.uk, .edu domains): e.g., University of Manchester, NHS education resources, university course materials.
3. **Authentic YouTube channels**: Only channels run by universities, professional medical/dental bodies (BDA, GDC, NHS, Royal Colleges), or verified educational creators with professional credentials.

You must NEVER cite Wikipedia, blogs, commercial health sites, social media, or unverified sources.

## REAL-AI FRAMEWORK INTEGRATION

### Pillar 1 — Reflective Integration
Before providing evidence, ALWAYS ask the student:
- "What do you already know about this topic?"
- "What do you expect the evidence might show?"
Only after they respond should you provide the full evidence-based answer. If they insist on a direct answer, gently explain why reflection first produces deeper learning, then provide the answer with a post-reflection prompt.

### Pillar 2 — Equity by Design
- Present diverse perspectives and global evidence where relevant
- Note when evidence may be limited to specific populations
- Use inclusive language and consider accessibility

### Pillar 3 — Authentic Clinical Alignment
- Always state the clinical relevance of evidence
- Include a **⚠️ Limitations** section noting what the evidence does NOT cover
- Flag when simulated/in-vitro evidence may not transfer to clinical settings
- Be transparent: "This AI response is a learning aid, not clinical advice"

### Pillar 4 — Learning-Centred Partnership
- Encourage the student to discuss findings with faculty
- Suggest how they might verify or extend the information
- Prompt: "How might you apply this in your next clinical session?"

## RESPONSE FORMAT
Structure your evidence-based responses as follows:

**📋 Pre-Reflection Prompt** (always first, unless student has already reflected)

Then after reflection:

**🔬 Evidence Summary**
Synthesise the key findings in clear, accessible language.

**📚 Key Sources**
List 3-5 specific references with:
- Author(s), Year, Title
- Journal name
- DOI or URL where available
- Brief note on evidence quality (RCT, systematic review, cohort study, etc.)

**🎓 University Resources**
Link to relevant Manchester or other university learning materials if applicable.

**🎥 Recommended Video**
Suggest 1-2 authentic YouTube videos from verified channels (university lectures, Royal College presentations, BDA/GDC content, etc.). Include channel name and why it's trustworthy.

**⚠️ Limitations & Transparency**
- What this evidence does NOT tell us
- Any biases or gaps in the literature
- "This AI-generated summary should be verified against primary sources"

**🤔 Post-Learning Reflection**
End with a reflective question: "Now that you've seen this evidence, how does it change or confirm your initial thinking?"

## CRITICAL RULES
- If you cannot find strong evidence from approved sources, say so honestly and suggest the most relevant authentic YouTube video as a starting point
- Never fabricate references — if unsure, say "I recommend searching PubMed for [specific terms]"
- Always distinguish between levels of evidence (systematic review > RCT > cohort > case report > expert opinion)
- When using web search, prioritise PubMed, university repositories, and professional body websites"""


EBL_SYSTEM_PROMPT = """You are the DentEdTech Enquiry-Based Learning (EBL) Facilitator. You guide medicine, dentistry, and pharmacology students through structured inquiry WITHOUT giving them direct answers or direct evidence. You operate under the REAL-AI framework.

## YOUR ROLE
You are a Socratic facilitator. Your job is to help students develop the PROCESS of inquiry, not to hand them conclusions. You must resist every temptation to provide direct answers, even when asked.

## THE HYBRID EBL MODEL
You guide students through a 5-phase inquiry cycle that combines a forming-storming-questioning model with Kolb's experiential learning:

### Phase 1: FORMING (Concrete Experience → Orientation)
Purpose: Encounter the problem and activate prior knowledge
Your prompts should:
- Present or help frame the clinical scenario/problem
- Ask: "What is your first reaction to this case?"
- Ask: "What do you already know that might be relevant?"
- Ask: "What feels familiar here, and what feels new or confusing?"
- Help students identify the BOUNDARIES of their current knowledge
DO NOT: Provide background information or context they haven't asked about

### Phase 2: STORMING (Reflective Observation → Divergent Thinking)
Purpose: Generate multiple perspectives and hypotheses
Your prompts should:
- Ask: "What are ALL the possible explanations? Don't filter yet."
- Ask: "What would a [periodontist/pharmacologist/radiologist] notice here that you might miss?"
- Ask: "What assumptions are you making? Can you name them?"
- Challenge groupthink: "You've all agreed quickly — what's the counterargument?"
- Encourage: "What if the opposite of your hypothesis were true?"
DO NOT: Validate or invalidate their hypotheses. Let ambiguity sit.

### Phase 3: QUESTIONING (Abstract Conceptualisation → Inquiry Design)
Purpose: Transform uncertainty into structured research questions
Your prompts should:
- Ask: "What specific questions do you need answered to move forward?"
- Help refine vague questions into searchable, answerable ones
- Ask: "Is this a question about mechanism, prevalence, treatment efficacy, or prognosis?"
- Guide PICO/PEO framework: "Who is the patient? What's the intervention? What are you comparing to? What outcome matters?"
- Ask: "How would you rank these questions by importance to the case?"
DO NOT: Provide the questions. Help them BUILD the questions themselves.

### Phase 4: SEEKING (Active Experimentation → Evidence Navigation)
Purpose: Learn WHERE and HOW to find evidence
Your prompts should:
- Ask: "Where would you look first? Why that source?"
- Guide search strategy: "What search terms would you use? How might you combine them?"
- Ask: "What type of evidence would best answer your question — a systematic review? An RCT? Clinical guidelines?"
- Prompt critical appraisal: "If you find a study, what would you check first to judge its quality?"
- Suggest databases WITHOUT searching for them: "PubMed, Cochrane Library, NICE guidelines — which fits your question type?"
- If stuck: "What if you searched [broader/narrower term]? What Boolean operators might help?"
DO NOT: Search for evidence, provide links, or summarise findings. Guide them to the water; don't pour it.

### Phase 5: SYNTHESISING (Reflection → Integration)
Purpose: Connect evidence back to the original problem
Your prompts should:
- Ask: "What did you find? How does it relate to the original case?"
- Ask: "Did the evidence confirm or challenge your initial thinking?"
- Ask: "What would you do differently next time you approach a similar case?"
- Ask: "What gaps remain? What would you want to investigate further?"
- Ask: "How would you explain your findings to the patient?"
- Prompt Kolb closure: "What's one principle you'll carry forward from this inquiry?"
DO NOT: Provide a summary. The student must synthesise.

## REAL-AI INTEGRATION

### Pillar 1 — Reflective Integration
- Every phase transition includes a reflection checkpoint
- Never provide terminal answers — always respond with a guiding question
- Use "What makes you think that?" before "Have you considered...?"

### Pillar 2 — Equity by Design
- In Phase 2, prompt consideration of diverse patient populations
- Ask: "Would this case unfold differently for a patient from a different background?"
- Encourage consideration of health inequalities and social determinants

### Pillar 3 — Authentic Clinical Alignment
- Ground all scenarios in realistic clinical contexts
- Ask: "In a real clinic, what constraints would you face that this scenario doesn't capture?"
- Remind students of the gap between textbook cases and clinical reality

### Pillar 4 — Learning-Centred Partnership
- Explicitly name when you're holding back an answer and why
- Encourage them to bring findings to their tutor/supervisor
- Normalise uncertainty: "Not knowing is the starting point of inquiry, not a failure"

## PHASE TRACKING
Always indicate which phase the student is in and when it's time to progress.
Use this format at the start of each response:
📍 **Phase [N]: [PHASE NAME]**

When transitioning, explain why: "You've generated strong questions — let's move to thinking about where to find answers."

## CRITICAL RULES
- NEVER provide direct evidence, citations, or links in EBL mode
- NEVER answer their clinical questions directly
- If they demand answers, explain: "In EBL, the process of finding the answer IS the learning. I can guide your search strategy, but the discovery needs to be yours."
- If they're truly stuck, offer a HINT (not an answer): "Consider looking at the mechanism of action..." not "The mechanism is..."
- You may provide a case scenario if the student asks for one to practise with
- Always maintain warmth and encouragement — inquiry is hard, and struggle is productive"""


# ─── Session State Initialization ───
def init_session():
    defaults = {
        "mode": None,
        "evidence_messages": [],
        "ebl_messages": [],
        "ebl_phase": 1,
        "ebl_case": None,
        "reflection_given": False,
        "discipline": "Dentistry",
        "year_of_study": "Year 3",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()


# ─── Helper Functions ───

def get_api_key():
    """Get API key from sidebar or secrets."""
    if "api_key" in st.session_state and st.session_state.api_key:
        return st.session_state.api_key
    return None


def call_claude(messages, system_prompt, use_search=False):
    """Call Claude API with optional web search."""
    api_key = get_api_key()
    if not api_key:
        return "⚠️ Please enter your Anthropic API key in the sidebar to continue."

    client = anthropic.Anthropic(api_key=api_key)

    kwargs = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": messages,
    }

    if use_search:
        kwargs["tools"] = [
            {
                "type": "web_search_20250305",
                "name": "web_search",
            }
        ]

    try:
        response = client.messages.create(**kwargs)

        # Extract text from response content blocks
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        return "\n".join(text_parts) if text_parts else "I wasn't able to generate a response. Please try again."

    except anthropic.AuthenticationError:
        return "⚠️ Invalid API key. Please check your Anthropic API key in the sidebar."
    except anthropic.RateLimitError:
        return "⚠️ Rate limit reached. Please wait a moment and try again."
    except Exception as e:
        return f"⚠️ An error occurred: {str(e)}"


def render_phase_stepper(current_phase):
    """Render the EBL phase progress stepper."""
    phases = [
        ("1", "Forming"),
        ("2", "Storming"),
        ("3", "Questioning"),
        ("4", "Seeking"),
        ("5", "Synthesising"),
    ]

    html = '<div class="phase-stepper">'
    for num, label in phases:
        phase_num = int(num)
        if phase_num < current_phase:
            dot_class = "phase-dot phase-dot-done"
            label_class = "phase-label"
            dot_content = "✓"
        elif phase_num == current_phase:
            dot_class = "phase-dot phase-dot-active"
            label_class = "phase-label phase-label-active"
            dot_content = num
        else:
            dot_class = "phase-dot phase-dot-pending"
            label_class = "phase-label"
            dot_content = num

        html += f"""
        <div class="phase-step">
            <div class="{dot_class}">{dot_content}</div>
            <div class="{label_class}">{label}</div>
        </div>"""

    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_message(role, content):
    """Render a chat message with styling."""
    if role == "user":
        css_class = "chat-msg chat-msg-user"
        icon = "🧑‍🎓"
    elif role == "system":
        css_class = "chat-msg chat-msg-system"
        icon = "🔔"
    else:
        css_class = "chat-msg chat-msg-assistant"
        icon = "🔬"

    st.markdown(
        f'<div class="{css_class}">{icon} {content}</div>',
        unsafe_allow_html=True,
    )


def render_real_ai_badges(pillars):
    """Render REAL-AI pillar badges."""
    badge_map = {
        "R": ("pillar-r", "Reflective Integration"),
        "E": ("pillar-e", "Equity by Design"),
        "A": ("pillar-a", "Authentic Alignment"),
        "L": ("pillar-l", "Learning Partnership"),
    }
    html = ""
    for p in pillars:
        cls, label = badge_map[p]
        html += f'<span class="pillar-badge {cls}">{label}</span>'
    return html


# ─── Sidebar ───
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 1rem 0 0.5rem;">
        <span style="font-family: 'DM Serif Display', serif; font-size: 1.5rem; color: #E8EDE9;">
            Dent<span style="color: #D4A853;">Ed</span>Tech
        </span>
        <div style="font-size: 0.72rem; color: #6B8577; margin-top: 0.2rem; letter-spacing: 0.08em; text-transform: uppercase;">
            Evidence Engine
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # API Key
    api_key_input = st.text_input(
        "Anthropic API Key",
        type="password",
        placeholder="sk-ant-...",
        help="Required to power the AI engine. Your key is not stored.",
        key="api_key",
    )

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # Student context
    st.markdown("##### 🎓 Your Profile")
    st.session_state.discipline = st.selectbox(
        "Discipline",
        ["Dentistry", "Medicine", "Pharmacology"],
        index=0,
    )
    st.session_state.year_of_study = st.selectbox(
        "Year of Study",
        ["Year 1", "Year 2", "Year 3", "Year 4", "Year 5", "Postgraduate"],
        index=2,
    )

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # REAL-AI Info
    with st.expander("📐 About the REAL-AI Framework"):
        st.markdown("""
        This platform is built on the **REAL-AI** framework for principled AI integration in health professions education:

        **R** — Reflective Integration
        *AI promotes critical thinking, not dependency*

        **E** — Equity by Design
        *Inclusive, unbiased, accessible learning*

        **A** — Authentic Clinical Alignment
        *Transparent about what AI can and cannot do*

        **L** — Learning-Centred Partnership
        *AI augments faculty, never replaces them*

        *Framework: Beyond the Algorithm (2026)*
        """)

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # Mode switch / Reset
    if st.session_state.mode is not None:
        if st.button("← Back to Mode Selection", use_container_width=True):
            st.session_state.mode = None
            st.rerun()

        if st.button("🔄 Reset Conversation", use_container_width=True):
            if st.session_state.mode == "evidence":
                st.session_state.evidence_messages = []
                st.session_state.reflection_given = False
            else:
                st.session_state.ebl_messages = []
                st.session_state.ebl_phase = 1
                st.session_state.ebl_case = None
            st.rerun()

    st.markdown("""
    <div class="app-footer">
        © 2026 DentEdTech<br>
        University of Manchester<br>
        <em>Not a substitute for clinical judgement</em>
    </div>
    """, unsafe_allow_html=True)


# ─── Main Content ───

# Header
st.markdown("""
<div class="main-header">
    <h1>Dent<span class="brand-accent">Ed</span>Tech Evidence Engine</h1>
    <div class="tagline">Theory-informed AI for health professions learning — built on the REAL-AI framework</div>
</div>
""", unsafe_allow_html=True)


# ─── Mode Selection ───
if st.session_state.mode is None:

    st.markdown(f"""
    <div style="text-align: center; margin-bottom: 2rem;">
        <span style="color: var(--text-secondary); font-size: 0.9rem;">
            Welcome, {st.session_state.discipline} student · {st.session_state.year_of_study} · University of Manchester
        </span>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown(f"""
        <div class="mode-card">
            <h3>🔬 Evidence-Based Knowledge</h3>
            <p>
                Ask clinical or scientific questions and receive evidence-based answers sourced
                exclusively from peer-reviewed journals, university resources, and verified
                educational videos.
            </p>
            <p>
                The engine will first prompt you to reflect on what you already know — building
                deeper learning through the Reflective Integration pillar.
            </p>
            <div style="margin-top: 0.8rem;">
                {render_real_ai_badges(["R", "A"])}
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Enter Evidence Mode →", key="btn_evidence", use_container_width=True):
            st.session_state.mode = "evidence"
            st.rerun()

    with col2:
        st.markdown(f"""
        <div class="mode-card">
            <h3>🧭 Enquiry-Based Learning</h3>
            <p>
                Develop your inquiry skills through a guided 5-phase cycle: Forming, Storming,
                Questioning, Seeking, and Synthesising. The AI will never give you direct
                answers — it guides you to discover them yourself.
            </p>
            <p>
                Combines problem-based learning with Kolb's experiential cycle for
                deep, transferable clinical reasoning.
            </p>
            <div style="margin-top: 0.8rem;">
                {render_real_ai_badges(["R", "E", "A", "L"])}
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Enter EBL Mode →", key="btn_ebl", use_container_width=True):
            st.session_state.mode = "ebl"
            # Set initial EBL welcome
            welcome = (
                "📍 **Phase 1: FORMING**\n\n"
                "Welcome to Enquiry-Based Learning. This is where your inquiry journey begins.\n\n"
                "You can either:\n"
                "- **Bring your own case** — describe a clinical scenario, lecture topic, or problem you're working through\n"
                "- **Ask me for a case** — tell me the subject area and I'll present a scenario for you to explore\n\n"
                "Before we begin, take a moment: *What topic or clinical area are you most curious about right now?*"
            )
            st.session_state.ebl_messages = [{"role": "assistant", "content": welcome}]
            st.rerun()

    # Framework overview
    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align: center; margin: 1rem 0 1.5rem;">
        <span style="font-family: 'DM Serif Display', serif; font-size: 1.1rem; color: var(--text-primary);">
            How the REAL-AI Framework Guides This Platform
        </span>
    </div>
    """, unsafe_allow_html=True)

    p1, p2, p3, p4 = st.columns(4, gap="medium")

    with p1:
        st.markdown("""
        <div class="mode-card" style="min-height: 180px;">
            <span class="pillar-badge pillar-r">R</span>
            <h3 style="font-size: 1rem !important;">Reflective Integration</h3>
            <p>AI pauses and prompts you to think before revealing answers. Your reasoning comes first.</p>
        </div>
        """, unsafe_allow_html=True)

    with p2:
        st.markdown("""
        <div class="mode-card" style="min-height: 180px;">
            <span class="pillar-badge pillar-e">E</span>
            <h3 style="font-size: 1rem !important;">Equity by Design</h3>
            <p>Diverse evidence, inclusive scenarios, and accessible design for all learners.</p>
        </div>
        """, unsafe_allow_html=True)

    with p3:
        st.markdown("""
        <div class="mode-card" style="min-height: 180px;">
            <span class="pillar-badge pillar-a">A</span>
            <h3 style="font-size: 1rem !important;">Authentic Alignment</h3>
            <p>Every response declares its limitations. Evidence is sourced, graded, and clinically contextualised.</p>
        </div>
        """, unsafe_allow_html=True)

    with p4:
        st.markdown("""
        <div class="mode-card" style="min-height: 180px;">
            <span class="pillar-badge pillar-l">L</span>
            <h3 style="font-size: 1rem !important;">Learning Partnership</h3>
            <p>AI supports your faculty, never replaces them. You're guided to grow, not to depend.</p>
        </div>
        """, unsafe_allow_html=True)


# ─── Evidence-Based Mode ───
elif st.session_state.mode == "evidence":

    st.markdown(f"""
    <div style="margin-bottom: 1.5rem;">
        <span style="font-family: 'DM Serif Display', serif; font-size: 1.4rem; color: var(--text-primary);">
            🔬 Evidence-Based Knowledge
        </span>
        <span style="margin-left: 1rem;">
            {render_real_ai_badges(["R", "A"])}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # Transparency notice
    st.markdown("""
    <div class="limitation-notice">
        <strong>⚠️ Pillar 3 — Transparency Statement:</strong>
        This AI searches peer-reviewed journals, university websites, and verified educational videos.
        It may not capture all available evidence. Always verify findings against primary sources
        and discuss with your supervisors. This tool does not replicate clinical reasoning under real-world conditions.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Display conversation history
    for msg in st.session_state.evidence_messages:
        render_message(msg["role"], msg["content"])

    # Input
    user_input = st.chat_input(
        "Ask a clinical or scientific question...",
        key="evidence_input",
    )

    if user_input:
        # Add user message
        st.session_state.evidence_messages.append(
            {"role": "user", "content": user_input}
        )
        render_message("user", user_input)

        # Build messages for API — include student context
        context_note = f"[Student context: {st.session_state.discipline}, {st.session_state.year_of_study}, University of Manchester]"
        api_messages = []
        for msg in st.session_state.evidence_messages:
            if msg["role"] == "user" and msg == st.session_state.evidence_messages[0]:
                api_messages.append({
                    "role": "user",
                    "content": f"{context_note}\n\n{msg['content']}"
                })
            else:
                api_messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        # Call Claude with web search enabled for evidence retrieval
        with st.spinner("Searching evidence-based sources..."):
            response = call_claude(
                api_messages,
                EVIDENCE_SYSTEM_PROMPT,
                use_search=True,
            )

        st.session_state.evidence_messages.append(
            {"role": "assistant", "content": response}
        )
        st.rerun()


# ─── EBL Mode ───
elif st.session_state.mode == "ebl":

    st.markdown(f"""
    <div style="margin-bottom: 1rem;">
        <span style="font-family: 'DM Serif Display', serif; font-size: 1.4rem; color: var(--text-primary);">
            🧭 Enquiry-Based Learning
        </span>
        <span style="margin-left: 1rem;">
            {render_real_ai_badges(["R", "E", "A", "L"])}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # Phase stepper
    render_phase_stepper(st.session_state.ebl_phase)

    # Phase descriptions
    phase_info = {
        1: ("Forming", "Encounter the problem. Activate what you already know. Identify the edges of your understanding."),
        2: ("Storming", "Generate hypotheses freely. Challenge assumptions. Explore multiple perspectives without filtering."),
        3: ("Questioning", "Transform your uncertainty into structured, searchable research questions."),
        4: ("Seeking", "Plan your evidence search strategy. Learn where and how to find reliable sources."),
        5: ("Synthesising", "Connect your findings back to the case. Reflect on what changed in your thinking."),
    }

    phase_name, phase_desc = phase_info[st.session_state.ebl_phase]
    st.markdown(f"""
    <div class="ebl-phase">
        <div class="ebl-phase-title">📍 Phase {st.session_state.ebl_phase}: {phase_name}</div>
        <div class="ebl-phase-desc">{phase_desc}</div>
    </div>
    """, unsafe_allow_html=True)

    # Transparency notice for EBL
    st.markdown("""
    <div class="limitation-notice">
        <strong>⚠️ EBL Commitment:</strong>
        This mode will NOT give you direct answers or evidence. It guides your inquiry process.
        The struggle of finding answers yourself is where deep learning happens.
        Bring your findings to your tutor for validation.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Display conversation history
    for msg in st.session_state.ebl_messages:
        render_message(msg["role"], msg["content"])

    # Phase navigation buttons
    nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
    with nav_col1:
        if st.session_state.ebl_phase > 1:
            if st.button("← Previous Phase"):
                st.session_state.ebl_phase -= 1
                transition_msg = f"📍 Moving back to **Phase {st.session_state.ebl_phase}: {phase_info[st.session_state.ebl_phase][0]}**\n\n{phase_info[st.session_state.ebl_phase][1]}"
                st.session_state.ebl_messages.append(
                    {"role": "assistant", "content": transition_msg}
                )
                st.rerun()
    with nav_col3:
        if st.session_state.ebl_phase < 5:
            if st.button("Next Phase →"):
                st.session_state.ebl_phase += 1
                transition_msg = f"📍 Progressing to **Phase {st.session_state.ebl_phase}: {phase_info[st.session_state.ebl_phase][0]}**\n\n{phase_info[st.session_state.ebl_phase][1]}\n\nLet's continue your inquiry."
                st.session_state.ebl_messages.append(
                    {"role": "assistant", "content": transition_msg}
                )
                st.rerun()

    # Input
    user_input = st.chat_input(
        "Share your thinking...",
        key="ebl_input",
    )

    if user_input:
        # Add user message
        st.session_state.ebl_messages.append(
            {"role": "user", "content": user_input}
        )
        render_message("user", user_input)

        # Build API messages with phase context
        context_note = (
            f"[Student context: {st.session_state.discipline}, {st.session_state.year_of_study}, "
            f"University of Manchester]\n"
            f"[Current EBL Phase: {st.session_state.ebl_phase} — {phase_info[st.session_state.ebl_phase][0]}]\n"
            f"[Facilitate according to Phase {st.session_state.ebl_phase} guidelines. "
            f"If the student seems ready to progress, suggest moving to the next phase.]"
        )

        api_messages = []
        for i, msg in enumerate(st.session_state.ebl_messages):
            if i == 0 and msg["role"] == "assistant":
                api_messages.append(msg)
            elif msg["role"] == "user" and i == len(st.session_state.ebl_messages) - 1:
                api_messages.append({
                    "role": "user",
                    "content": f"{context_note}\n\n{msg['content']}"
                })
            else:
                api_messages.append(msg)

        # Call Claude WITHOUT web search (EBL must not provide evidence)
        with st.spinner("Reflecting on your inquiry..."):
            response = call_claude(
                api_messages,
                EBL_SYSTEM_PROMPT,
                use_search=False,
            )

        # Check if AI suggests phase transition
        if st.session_state.ebl_phase < 5:
            transition_keywords = {
                1: ["move to storming", "phase 2", "ready to storm", "let's storm"],
                2: ["move to questioning", "phase 3", "ready to question", "form your questions"],
                3: ["move to seeking", "phase 4", "ready to seek", "where to look"],
                4: ["move to synthesising", "phase 5", "ready to synthesise", "bring it together"],
            }
            check_keys = transition_keywords.get(st.session_state.ebl_phase, [])
            if any(kw in response.lower() for kw in check_keys):
                st.session_state.ebl_phase += 1

        st.session_state.ebl_messages.append(
            {"role": "assistant", "content": response}
        )
        st.rerun()
