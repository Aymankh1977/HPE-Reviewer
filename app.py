import streamlit as st
import os
import ast
import datetime
from io import BytesIO
from docx import Document
from dotenv import load_dotenv
from anthropic import Anthropic
from pypdf import PdfReader
from duckduckgo_search import DDGS

# --- Page Config ---
st.set_page_config(
    page_title="HPE Expert Reviewer (Forensic)",
    page_icon="🔎",
    layout="wide"
)

# --- SECURE KEY HANDLING ---
try:
    if "ANTHROPIC_API_KEY" in st.secrets:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    else:
        load_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY")
except FileNotFoundError:
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    st.error("🚨 Configuration Error: ANTHROPIC_API_KEY is missing. Please add it to Streamlit Secrets.")
    st.stop()

client = Anthropic(api_key=api_key)

# --- Session State ---
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "full_text" not in st.session_state: st.session_state.full_text = ""
if "analysis_report" not in st.session_state: st.session_state.analysis_report = ""

# --- Sidebar ---
with st.sidebar:
    st.title("🔎 HPE Reviewer Plus")
    st.markdown("Forensic Analysis & Expert Review")
    uploaded_file = st.file_uploader("Upload Manuscript (PDF)", type="pdf")
    if st.button("Clear / Reset"):
        st.session_state.chat_history = []
        st.session_state.full_text = ""
        st.session_state.analysis_report = ""
        st.rerun()

# --- Helper Functions ---

def get_pdf_text_with_pages(uploaded_file):
    """Extracts text but inserts [Page X] markers for specific referencing."""
    try:
        reader = PdfReader(uploaded_file)
        text = ""
        for i, page in enumerate(reader.pages):
            content = page.extract_text()
            if content:
                # Inject page marker
                text += f"\n\n--- [Page {i+1}] ---\n\n{content}"
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None

def create_docx(report_text):
    doc = Document()
    doc.add_heading('HPE Expert Review Report', 0)
    for line in report_text.split('\n'):
        line = line.strip()
        if not line: continue
        if line.startswith('###') or line.startswith('**') and len(line) < 60:
            doc.add_heading(line.replace('#', '').replace('*', '').strip(), level=2)
        else:
            doc.add_paragraph(line)
    bio = BytesIO()
    doc.save(bio)
    return bio.getvalue()

def search_evidence(query):
    try:
        results = DDGS().text(query, max_results=3)
        if results:
            return "\n".join([f"- {r['title']}: {r['body']} (Source: {r['href']})" for r in results])
        return "No results found."
    except: return "Search unavailable."

def analyze_manuscript(client, text):
    status = st.status("🔍 Starting Forensic Analysis...", expanded=True)
    
    # --- PHASE 1: FORENSIC SCAN ---
    status.write("🧠 Phase 1: Scanning for Logic, Dates, and Technical Accuracy...")
    
    current_year = datetime.datetime.now().year
    
    system_prompt = (
        "You are an expert, detail-oriented peer reviewer for top medical education journals. "
        "You verify facts, check consistency, and act as a forensic editor."
    )
    
    # This prompt is designed to catch the specific errors you mentioned
    prompt_phase1 = f"""
    Analyze this manuscript text (with Page markers included):
    <manuscript>
    {text[:120000]} 
    </manuscript>

    You must perform a 'Sanity Check' and 'Consistency Scan'.
    
    TASK: Identify specific items that need external verification. Look for:
    1. **Temporal Logic**: Are there dates in the future (e.g., > {current_year})? Are citations newer than the study date?
    2. **Technical Accuracy**: Check for non-existent technologies (e.g., 'GPT-5', 'iPhone 20') or made-up statistics.
    3. **Methodological Citations**: Are the methods referenced correctly?
    
    OUTPUT: A Python list of strings for items to search/verify.
    Example: ["Release date of GPT-5", "Current date vs Manuscript date 2026", "Citation check for Smith 2024"]
    """
    
    msg1 = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt_phase1}]
    )
    
    try:
        raw = msg1.content[0].text
        start, end = raw.find('['), raw.rfind(']') + 1
        queries = ast.literal_eval(raw[start:end])
    except:
        queries = ["Current trends in medical education", "GPT-4 release date"]

    # --- PHASE 2: EVIDENCE GATHERING ---
    status.write(f"🌐 Phase 2: Fact-Checking {len(queries)} specific claims...")
    evidence = ""
    for q in queries:
        if isinstance(q, str):
            res = search_evidence(q)
            evidence += f"Claim/Query: {q}\nResult: {res}\n\n"

    # --- PHASE 3: DEEP REPORT GENERATION ---
    status.write("📝 Phase 3: Writing Comprehensive Expert Report...")
    
    final_prompt = f"""
    You are the Senior Editor. Write a detailed Peer Review Report based on the manuscript and the fact-check evidence below.
    
    <fact_check_evidence>
    {evidence}
    </fact_check_evidence>

    **CRITICAL INSTRUCTIONS:**
    1. **Accuracy**: If the author mentions "GPT-5" or future dates like "2026", FLAGGED IT as a major error based on the evidence.
    2. **Content Comprehension**: Do not say "No results found" if the results are just unstructured. Look for *implied* results in the text.
    3. **Specificity**: Quote specific [Page X] numbers when pointing out errors.
    
    **REPORT STRUCTURE:**
    
    1. **Executive Summary**: (Accept, Minor, Major, Reject). Balance strengths and weaknesses.
    2. **Forensic Sanity Check** (New Section):
       - **Temporal Logic**: Flag date inconsistencies (e.g., submission date vs search dates).
       - **Technical Accuracy**: Flag non-existent models/tools.
    3. **Internal Consistency**:
       - Do the Results match the Methods?
       - Does the Abstract match the Conclusion?
    4. **Methodological Critique**:
       - Sample size, Ethics, Data analysis.
    5. **Specific Comments (Line-by-Line)**:
       - Use [Page X] references.
       - Point out missing citations or logical gaps.
    6. **Constructive Recommendations**:
       - Be specific. (e.g., "Add a Table comparing X and Y", "Rename section Z to...").

    Tone: Rigorous, Academic, Constructive.
    """
    
    st.session_state.chat_history.append({"role": "user", "content": prompt_phase1})
    st.session_state.chat_history.append({"role": "assistant", "content": raw})
    st.session_state.chat_history.append({"role": "user", "content": final_prompt})

    final_msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4000,
        system=system_prompt,
        messages=st.session_state.chat_history
    )
    
    report = final_msg.content[0].text
    st.session_state.chat_history.append({"role": "assistant", "content": report})
    status.update(label="✅ Review Complete!", state="complete", expanded=False)
    return report

# --- Main App ---

if uploaded_file and not st.session_state.full_text:
    text = get_pdf_text_with_pages(uploaded_file)
    if text:
        st.session_state.full_text = text
        st.success(f"PDF Loaded with Page Markers: {len(text)} chars.")

if st.session_state.full_text and not st.session_state.analysis_report:
    if st.button("🚀 Start Forensic Analysis"):
        report = analyze_manuscript(client, st.session_state.full_text)
        st.session_state.analysis_report = report
        st.rerun()

if st.session_state.analysis_report:
    tab1, tab2 = st.tabs(["📝 Forensic Report", "💬 Expert Chat"])
    
    with tab1:
        st.markdown(st.session_state.analysis_report)
        docx = create_docx(st.session_state.analysis_report)
        st.download_button("Download Report (Word)", docx, "Review_Report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    
    with tab2:
        st.markdown("### Ask follow-up questions")
        for msg in st.session_state.chat_history:
            if len(msg['content']) < 2000:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        if prompt := st.chat_input("Ask about specific page errors or citations..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                stream = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1024,
                    messages=st.session_state.chat_history,
                    stream=True
                )
                def generator():
                    for event in stream:
                        if event.type == "content_block_delta": yield event.delta.text
                response = st.write_stream(generator)
            st.session_state.chat_history.append({"role": "assistant", "content": response})

else:
    if not uploaded_file:
        st.info("👈 Upload PDF to begin.")