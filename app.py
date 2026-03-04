import streamlit as st
import os
from io import BytesIO
from docx import Document
from dotenv import load_dotenv
from anthropic import Anthropic
from pypdf import PdfReader

# --- CONFIGURATION ---
st.set_page_config(page_title="HPE Expert Reviewer (Sonnet)", page_icon="🎓", layout="wide")

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

# --- MODEL SETTINGS (Based on your snippet) ---
MODEL_NAME = "claude-3-sonnet-20240229"
MAX_TOKENS = 4096  # Increased limit for deeper analysis
client = Anthropic(api_key=api_key)

# --- SESSION STATE ---
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "full_text" not in st.session_state: st.session_state.full_text = ""
if "analysis_report" not in st.session_state: st.session_state.analysis_report = ""

# --- HELPER FUNCTIONS ---
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

# --- CORE ANALYSIS LOGIC ---
def analyze_manuscript(text):
    status = st.status("🔍 Starting Expert Analysis (Claude 3 Sonnet)...", expanded=True)
    
    # --- STEP 1: CITATION MAPPING ---
    status.write("📚 Phase 1: Mapping References & Checking Logic...")
    
    # We ask Sonnet to understand the references first
    audit_prompt = f"""
    Read this manuscript (Context window optimized):
    {text[:100000]} 
    
    Perform a pre-analysis check:
    1. Scan the References list.
    2. Check if the in-text citations match the list.
    3. Identify the core Research Question and Conclusion.
    
    Return a brief 'Audit Summary' of these findings.
    """
    
    try:
        audit_msg = client.messages.create(
            model=MODEL_NAME, max_tokens=2000, 
            messages=[{"role": "user", "content": audit_prompt}]
        )
        citation_health = audit_msg.content[0].text
    except Exception as e:
        st.error(f"Error accessing Model: {e}")
        status.update(label="Error", state="error")
        return "Error"

    # --- STEP 2: CRITICAL REVIEW ---
    status.write("🧠 Phase 2: Writing Expert Review...")
    
    system_prompt = (
        "You are a Senior Academic Editor. You provide high-level, constructive, and rigorous peer reviews. "
        "You DO NOT assume errors; you verify them against the text."
    )
    
    final_prompt = f"""
    MANUSCRIPT TEXT:
    {text[:100000]}
    
    PRE-ANALYSIS FINDINGS:
    {citation_health}
    
    TASK: Write a Comprehensive Peer Review Report.
    
    1. **Executive Summary**: Recommendation (Accept/Reject/Revise).
    2. **Logic & Flow**: Analyze the alignment (Gap -> RQ -> Methods -> Conclusion).
    3. **Methodology**: Specific critique of design and ethics.
    4. **Reference Quality**: Comment on the citations based on your audit.
    5. **Specific Comments**: Line-by-line feedback with quotes.
    6. **Actionable Recommendations**: How to fix the paper.
    """
    
    # Save prompts to history
    st.session_state.chat_history.append({"role": "user", "content": final_prompt})
    
    final_msg = client.messages.create(
        model=MODEL_NAME, max_tokens=MAX_TOKENS, system=system_prompt,
        messages=[{"role": "user", "content": final_prompt}]
    )
    
    report = final_msg.content[0].text
    st.session_state.chat_history.append({"role": "assistant", "content": report})
    
    status.update(label="Analysis Complete", state="complete", expanded=False)
    return report

# --- UI LAYOUT ---
with st.sidebar:
    st.title("🎓 HPE Expert Reviewer")
    st.caption(f"Model: {MODEL_NAME}")
    uploaded_file = st.file_uploader("Upload Manuscript (PDF)", type="pdf")
    if st.button("Reset System"):
        st.session_state.clear()
        st.rerun()

# --- MAIN APP ---
if uploaded_file and not st.session_state.full_text:
    text = get_pdf_text(uploaded_file)
    if text:
        st.session_state.full_text = text
        st.success(f"Manuscript Loaded: {len(text)} characters.")

if st.session_state.full_text and not st.session_state.analysis_report:
    if st.button("🚀 Start Expert Analysis"):
        report = analyze_manuscript(st.session_state.full_text)
        if report != "Error":
            st.session_state.analysis_report = report
            st.rerun()

if st.session_state.analysis_report:
    tab1, tab2 = st.tabs(["📝 Review Report", "💬 Editor Chat"])
    
    with tab1:
        st.markdown(st.session_state.analysis_report)
        st.download_button("Download Report (Word)", create_docx(st.session_state.analysis_report), "Review.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    
    with tab2:
        st.info("Ask questions about the review or the manuscript.")
        
        # Display clean history
        for msg in st.session_state.chat_history:
             if msg['role'] != 'user' or "MANUSCRIPT TEXT" not in msg['content']: 
                 if len(msg['content']) < 4000:
                    st.chat_message(msg["role"]).markdown(msg["content"])
        
        if prompt := st.chat_input("Ex: 'Clarify the methodology weakness'"):
            st.chat_message("user").markdown(prompt)
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            with st.chat_message("assistant"):
                # System prompt passed separately
                sys_prompt = "You are a helpful Senior Editor. Use the manuscript and review to answer accurately."
                
                # Context construction
                msgs = [
                    {"role": "user", "content": f"Manuscript Context:\n{st.session_state.full_text[:50000]}..."},
                    {"role": "assistant", "content": "I have read the manuscript."},
                    {"role": "user", "content": f"Critique Context:\n{st.session_state.analysis_report}"},
                    {"role": "assistant", "content": "I have the critique ready."}
                ]
                
                # Append recent history
                for m in st.session_state.chat_history[-4:]:
                    msgs.append(m)
                
                # Append current prompt
                msgs.append({"role": "user", "content": prompt})

                stream = client.messages.create(
                    model=MODEL_NAME, 
                    max_tokens=2000, 
                    system=sys_prompt,
                    messages=msgs, 
                    stream=True
                )
                response = st.write_stream(chunk.delta.text for chunk in stream if chunk.type == "content_block_delta")
            
            st.session_state.chat_history.append({"role": "assistant", "content": response})
else:
    if not uploaded_file: st.info("👈 Upload PDF to begin.")