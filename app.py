import streamlit as st
import os
import ast
from io import BytesIO
from docx import Document
from dotenv import load_dotenv
from anthropic import Anthropic
from pypdf import PdfReader
from duckduckgo_search import DDGS

# --- Page Config ---
st.set_page_config(page_title="HPE Expert Reviewer (Deep Logic)", page_icon="⚖️", layout="wide")

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

# --- MODEL CONFIG ---
MODEL_NAME = "claude-3-haiku-20240307" 
client = Anthropic(api_key=api_key)

# --- SESSION STATE ---
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "full_text" not in st.session_state: st.session_state.full_text = ""
if "analysis_report" not in st.session_state: st.session_state.analysis_report = ""

# --- HELPERS ---
def get_pdf_text(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None

def create_docx(report_text):
    doc = Document()
    doc.add_heading('Expert Peer Review Report', 0)
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
        return "\n".join([f"- {r['title']} ({r['href']})" for r in results]) if results else "No results."
    except: return "Search unavailable."

# --- CORE LOGIC ---
def analyze_manuscript(text):
    status = st.status("🔍 Deep Analysis in Progress...", expanded=True)
    
    # 1. THE "DEEP READ" & EVIDENCE GATHERING
    status.write("🧠 Phase 1: Identifying key claims for verification...")
    
    scan_prompt = f"""
    Read this manuscript text:
    {text[:80000]}
    
    Identify 3 SPECIFIC factual claims, dates, or citations that seem suspicious or require checking.
    Return ONLY a Python list of strings. Example: ["Submission date 2026 vs Search date 2024", "Citation coverage of GPT-4"]
    """
    
    msg1 = client.messages.create(
        model=MODEL_NAME, max_tokens=1000, 
        messages=[{"role": "user", "content": scan_prompt}]
    )
    
    try:
        raw = msg1.content[0].text
        start, end = raw.find('['), raw.rfind(']') + 1
        queries = ast.literal_eval(raw[start:end])
    except:
        queries = ["Medical education research methodology"]
        
    # 2. EVIDENCE FETCH
    status.write(f"🌐 Phase 2: Verifying {len(queries)} specific claims...")
    evidence = ""
    for q in queries:
        res = search_evidence(q)
        evidence += f"Check: {q}\nResult: {res}\n\n"

    # 3. THE EXPERT CRITIQUE (CHAIN OF THOUGHT)
    status.write("📝 Phase 3: Synthesizing Expert Review...")
    
    system_prompt = (
        "You are a Senior Editor for 'Medical Teacher'. "
        "You are famous for being 'Rigorous, Skeptical, and Constructive'. "
        "You DO NOT accept generic statements. "
        "You MUST quote the text to prove your critique."
    )
    
    final_prompt = f"""
    MANUSCRIPT TEXT:
    {text[:120000]}
    
    EXTERNAL VERIFICATION DATA:
    {evidence}
    
    TASK: Write a robust Peer Review Report.
    
    **STEP 1: INTERNAL LOGIC CHECK (Mental Scratchpad)**
    - Identify the Research Question (RQ).
    - Identify the Methods.
    - Identify the Conclusion.
    - Ask: Do they align? (The Golden Thread).
    - Ask: Are there contradictions? (e.g. Abstract says X, Results say Y).
    
    **STEP 2: WRITE THE REPORT**
    Use this structure:
    
    1. **Executive Summary & Decision** (Accept/Reject/Revise).
    2. **The Logic & Alignment Check**:
       - Critique the "Golden Thread". Does the RQ match the Conclusion?
       - Point out contradictions using QUOTES from the text.
    3. **Methodological Rigor**:
       - Critique Sample Size, Ethics, and Data Analysis. 
       - Be specific (e.g., "The authors claim grounded theory but used thematic analysis").
    4. **Forensic Accuracy Check**:
       - Use the 'External Verification Data' above.
       - Highlight date errors (e.g., 2026 submission vs 2024 data).
       - Highlight technical errors (e.g., hallucinated models).
    5. **Specific Section Comments**:
       - Intro: Is the gap real?
       - Methods: Is it reproducible?
       - Results: Over-interpreted?
    6. **Actionable Fixes**:
       - Specific instructions (e.g., "Create a table comparing X...", "Delete paragraph 2").

    Tone: High-level Academic.
    """
    
    final_msg = client.messages.create(
        model=MODEL_NAME, max_tokens=4000, system=system_prompt,
        messages=[{"role": "user", "content": final_prompt}]
    )
    
    report = final_msg.content[0].text
    status.update(label="Analysis Complete", state="complete", expanded=False)
    return report

# --- UI ---
with st.sidebar:
    st.title("⚖️ HPE Expert Reviewer")
    st.markdown("Deep Logic + Evidence Check")
    uploaded_file = st.file_uploader("Upload Manuscript (PDF)", type="pdf")
    if st.button("Reset"):
        st.session_state.clear()
        st.rerun()

if uploaded_file and not st.session_state.full_text:
    text = get_pdf_text(uploaded_file)
    if text:
        st.session_state.full_text = text
        st.success(f"Loaded {len(text)} characters.")

if st.session_state.full_text and not st.session_state.analysis_report:
    if st.button("🚀 Start Deep Analysis"):
        report = analyze_manuscript(st.session_state.full_text)
        st.session_state.analysis_report = report
        st.rerun()

if st.session_state.analysis_report:
    tab1, tab2 = st.tabs(["📝 Review Report", "💬 Expert Chat"])
    
    with tab1:
        st.markdown(st.session_state.analysis_report)
        st.download_button("Download Report (Word)", create_docx(st.session_state.analysis_report), "Review.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    
    with tab2:
        st.markdown("### Ask follow-up questions")
        
        # Display clean history
        for msg in st.session_state.chat_history:
             st.chat_message(msg["role"]).markdown(msg["content"])
        
        if prompt := st.chat_input("Ex: 'Rewrite the abstract to fix the logic gap'"):
            st.chat_message("user").markdown(prompt)
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            with st.chat_message("assistant"):
                # --- FIXED CHAT LOGIC ---
                # 1. System prompt goes in 'system' param, not messages list.
                chat_system_prompt = "You are a co-author helping fix the paper based on the review. Be academic and precise."
                
                # 2. Construct context messages correctly (User -> Assistant -> User)
                # We seed the context as the first interaction
                msgs = [
                    {
                        "role": "user", 
                        "content": f"Here is the manuscript context (truncated):\n{st.session_state.full_text[:30000]}\n\nAnd here is the critique report:\n{st.session_state.analysis_report}"
                    },
                    {
                        "role": "assistant", 
                        "content": "I have read the manuscript and the critique. I am ready to help you improve the paper."
                    }
                ]
                
                # 3. Append the actual conversation history
                for m in st.session_state.chat_history:
                    msgs.append(m)
                
                # 4. API Call
                stream = client.messages.create(
                    model=MODEL_NAME, 
                    max_tokens=2000, 
                    system=chat_system_prompt, # SYSTEM PROMPT HERE
                    messages=msgs, 
                    stream=True
                )
                response = st.write_stream(chunk.delta.text for chunk in stream if chunk.type == "content_block_delta")
            
            st.session_state.chat_history.append({"role": "assistant", "content": response})
else:
    if not uploaded_file: st.info("👈 Upload PDF to start.")