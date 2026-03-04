import streamlit as st
import os
from io import BytesIO
from docx import Document
from dotenv import load_dotenv
from anthropic import Anthropic
from pypdf import PdfReader

# --- CONFIGURATION ---
st.set_page_config(page_title="HPE Expert Reviewer (Sonnet Edition)", page_icon="🎓", layout="wide")

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

# --- CRITICAL CHANGE: USING INTELLIGENT MODEL ---
# Switched from Haiku to Sonnet 3.5 for expert reasoning and citation checking
MODEL_NAME = "claude-3-5-sonnet-20240620"
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
    status = st.status("🔍 Starting Expert Analysis (Claude 3.5 Sonnet)...", expanded=True)
    
    # --- STEP 1: CITATION AUDIT ---
    status.write("📚 Phase 1: Auditing References & Bibliography...")
    
    # We explicitly ask the model to map citations first.
    audit_prompt = f"""
    You are a forensic editor. Read this manuscript:
    {text[:150000]} 
    
    Task: Perform a 'Citation Audit'.
    1. Look at the Reference List at the end.
    2. Look at the in-text citations (e.g., (Smith, 2020) or [1]).
    3. Check: Are there in-text citations missing from the Reference list?
    4. Check: Are there References listed that are never used in the text?
    5. Check: Are the dates consistent?
    
    Return a short summary of the Citation Health.
    """
    
    audit_msg = client.messages.create(
        model=MODEL_NAME, max_tokens=1500, 
        messages=[{"role": "user", "content": audit_prompt}]
    )
    citation_health = audit_msg.content[0].text
    
    # --- STEP 2: CRITICAL REVIEW ---
    status.write("🧠 Phase 2: Generating Deep Critical Review...")
    
    system_prompt = (
        "You are a Senior Editor for 'Medical Teacher' and 'BMC Medical Education'. "
        "Your reviews are EVIDENCE-BASED. "
        "You NEVER assume an error exists unless you can prove it from the text. "
        "You focus on 'Constructive Alignment' (Gap -> Question -> Methods -> Results)."
    )
    
    final_prompt = f"""
    MANUSCRIPT TEXT:
    {text[:150000]}
    
    CITATION AUDIT FINDINGS:
    {citation_health}
    
    TASK: Write a Comprehensive Peer Review Report.
    
    INSTRUCTIONS:
    1. **Do not hallucinate errors.** If you claim a methodology flaw, QUOTE the sentence in the text that shows the flaw.
    2. **Use the Citation Audit.** Use the findings provided above to comment on the reference quality.
    3. **Tone:** Professional, objective, expert. Not harsh for the sake of being harsh.
    
    REPORT SECTIONS:
    1. **Executive Summary**: Brief overview and decision recommendation.
    2. **Logic & Flow**: Does the 'Golden Thread' hold? (Alignment of RQ -> Methods -> Conclusion).
    3. **Methodological Critique**: Specific feedback on Sample, Design, and Analysis.
    4. **Citation & Reference Quality**: (Insert the Citation Audit findings here).
    5. **Specific Comments**: Line-by-line feedback.
    6. **Actionable Recommendations**: Clear steps for the authors.
    """
    
    # Save prompts to history so Chat knows them
    st.session_state.chat_history.append({"role": "user", "content": final_prompt})
    
    final_msg = client.messages.create(
        model=MODEL_NAME, max_tokens=4000, system=system_prompt,
        messages=[{"role": "user", "content": final_prompt}]
    )
    
    report = final_msg.content[0].text
    st.session_state.chat_history.append({"role": "assistant", "content": report})
    
    status.update(label="Expert Analysis Complete", state="complete", expanded=False)
    return report

# --- UI LAYOUT ---
with st.sidebar:
    st.title("🎓 HPE Expert Reviewer")
    st.caption("Model: Claude 3.5 Sonnet")
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
        
        if prompt := st.chat_input("Ex: 'Where exactly is the reference mismatch?'"):
            st.chat_message("user").markdown(prompt)
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            with st.chat_message("assistant"):
                # System prompt passed separately to avoid BadRequestError
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