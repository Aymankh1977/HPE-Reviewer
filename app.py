import streamlit as st
import os
from io import BytesIO
from docx import Document
from dotenv import load_dotenv
from anthropic import Anthropic, NotFoundError
from pypdf import PdfReader

# --- CONFIGURATION ---
st.set_page_config(page_title="HPE Expert Reviewer (Hybrid)", page_icon="🎓", layout="wide")

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

# --- MODELS ---
# We try the smartest first. If it fails, we fall back to the fast one with "Smart Prompting"
SMART_MODEL = "claude-3-5-sonnet-20240620"
FAST_MODEL = "claude-3-haiku-20240307"

# --- SESSION STATE ---
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "full_text" not in st.session_state: st.session_state.full_text = ""
if "analysis_report" not in st.session_state: st.session_state.analysis_report = ""
if "current_model" not in st.session_state: st.session_state.current_model = "Unknown"

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

# --- INTELLIGENT AGENT LOGIC ---
def analyze_manuscript(text):
    status = st.status("🔍 Initializing Analysis Agents...", expanded=True)
    
    # 1. ATTEMPT WITH SMART MODEL (SONNET 3.5)
    try:
        status.write(f"🧠 Attempting Analysis with {SMART_MODEL}...")
        
        system_prompt = (
            "You are a Senior Editor for 'Medical Teacher'. Your job is to be rigorous and specific. "
            "You do not hallucinate errors. You quote the text to prove flaws."
        )
        
        user_prompt = f"""
        MANUSCRIPT:
        {text[:150000]}
        
        Task: Write a Critical Peer Review Report.
        1. Check the Reference List vs In-Text citations.
        2. Check the 'Golden Thread' (Logic Flow).
        3. Critique the Methodology against standard guidelines (CONSORT/SRQR).
        
        Output a structured report with Executive Summary, Method Critique, Citation Check, and Line-by-Line comments.
        """
        
        msg = client.messages.create(
            model=SMART_MODEL,
            max_tokens=4000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        
        st.session_state.current_model = "Claude 3.5 Sonnet (Expert Mode)"
        status.update(label="Analysis Complete (Expert Mode)", state="complete", expanded=False)
        return msg.content[0].text

    except NotFoundError:
        # 2. FALLBACK TO HAIKU WITH "CHAIN OF THOUGHT" (SUPER PROMPT)
        status.write("⚠️ Expert Model not available. Switching to Enhanced Haiku Logic...")
        st.session_state.current_model = "Claude 3 Haiku (Enhanced Logic Mode)"
        
        # Step A: Logic Map (Force Haiku to understand structure first)
        status.write("⚙️ Step 1: Mapping Logic Structure...")
        logic_prompt = f"""
        Read this text: {text[:100000]}
        Identify:
        1. Research Question.
        2. Methodology Used.
        3. Conclusion.
        4. Any mismatch between them.
        Return ONLY a summary of these 4 points.
        """
        logic_msg = client.messages.create(
            model=FAST_MODEL, max_tokens=1000, messages=[{"role": "user", "content": logic_prompt}]
        )
        logic_summary = logic_msg.content[0].text
        
        # Step B: Final Critique (Feed the logic map back to Haiku)
        status.write("⚙️ Step 2: Generating Critical Report...")
        final_prompt = f"""
        MANUSCRIPT: {text[:100000]}
        
        LOGIC ANALYSIS: {logic_summary}
        
        Using the Logic Analysis above, write a RIGOROUS Peer Review Report.
        - Be harsh but fair.
        - Point out where the Conclusion does not match the Question.
        - Critique the Methodology.
        - Provide Actionable Recommendations.
        """
        
        final_msg = client.messages.create(
            model=FAST_MODEL, max_tokens=4000, 
            system="You are a critical academic reviewer. Focus on logic gaps.",
            messages=[{"role": "user", "content": final_prompt}]
        )
        
        status.update(label="Analysis Complete (Enhanced Mode)", state="complete", expanded=False)
        return final_msg.content[0].text

    except Exception as e:
        status.update(label="Error", state="error")
        st.error(f"Unexpected Error: {e}")
        return None

# --- UI LAYOUT ---
with st.sidebar:
    st.title("🎓 HPE Expert Reviewer")
    st.caption("Auto-Switching Hybrid Engine")
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
    if st.button("🚀 Start Hybrid Analysis"):
        report = analyze_manuscript(st.session_state.full_text)
        if report:
            st.session_state.analysis_report = report
            st.rerun()

if st.session_state.analysis_report:
    st.success(f"Generated using: **{st.session_state.current_model}**")
    
    tab1, tab2 = st.tabs(["📝 Review Report", "💬 Editor Chat"])
    
    with tab1:
        st.markdown(st.session_state.analysis_report)
        st.download_button("Download Report (Word)", create_docx(st.session_state.analysis_report), "Review.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    
    with tab2:
        st.info("Ask questions about the review or the manuscript.")
        
        for msg in st.session_state.chat_history:
             if msg['role'] != 'user': 
                 if len(msg['content']) < 4000:
                    st.chat_message(msg["role"]).markdown(msg["content"])
        
        if prompt := st.chat_input("Ex: 'Expand on the methodology critique'"):
            st.chat_message("user").markdown(prompt)
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            with st.chat_message("assistant"):
                # Use the model that worked for the analysis
                ACTIVE_MODEL = SMART_MODEL if "Sonnet" in st.session_state.current_model else FAST_MODEL
                
                try:
                    stream = client.messages.create(
                        model=ACTIVE_MODEL, 
                        max_tokens=2000, 
                        system="You are a helpful Senior Editor.",
                        messages=[
                            {"role": "user", "content": f"Context: {st.session_state.analysis_report}"},
                            {"role": "assistant", "content": "I understand the critique."},
                            {"role": "user", "content": prompt}
                        ], 
                        stream=True
                    )
                    response = st.write_stream(chunk.delta.text for chunk in stream if chunk.type == "content_block_delta")
                except NotFoundError:
                    # Fallback for chat too if Sonnet fails mid-chat
                    stream = client.messages.create(
                        model=FAST_MODEL, 
                        max_tokens=2000, 
                        system="You are a helpful Senior Editor.",
                        messages=[
                            {"role": "user", "content": f"Context: {st.session_state.analysis_report}"},
                            {"role": "assistant", "content": "I understand the critique."},
                            {"role": "user", "content": prompt}
                        ], 
                        stream=True
                    )
                    response = st.write_stream(chunk.delta.text for chunk in stream if chunk.type == "content_block_delta")

            st.session_state.chat_history.append({"role": "assistant", "content": response})
else:
    if not uploaded_file: st.info("👈 Upload PDF to begin.")