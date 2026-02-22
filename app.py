import streamlit as st
import os
import ast
from dotenv import load_dotenv
from anthropic import Anthropic
from pypdf import PdfReader
from duckduckgo_search import DDGS

# --- Page Config ---
st.set_page_config(
    page_title="HPE Expert Reviewer",
    page_icon="🧬",
    layout="wide"
)

# --- SECURE API KEY HANDLING ---
# This looks for the key in Streamlit Cloud Secrets OR local .env file
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

# --- Session State Management ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "full_text" not in st.session_state:
    st.session_state.full_text = ""
if "analysis_report" not in st.session_state:
    st.session_state.analysis_report = ""

# --- Sidebar ---
with st.sidebar:
    st.title("🧬 HPE Reviewer")
    st.markdown("Automated expert peer review for *Medical Teacher*, *BMC Med Ed*, etc.")
    
    # NO API KEY INPUT HERE (Secure Mode)
    
    uploaded_file = st.file_uploader("Upload Manuscript (PDF)", type="pdf")
    
    if st.button("Clear / Reset"):
        st.session_state.chat_history = []
        st.session_state.full_text = ""
        st.session_state.analysis_report = ""
        st.rerun()

# --- Helper Functions ---

def get_pdf_text(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None

def search_evidence(query):
    """Searches the web for evidence/citations."""
    try:
        results = DDGS().text(query, max_results=3)
        if results:
            summary = "\n".join([f"- {r['title']}: {r['body']} (Source: {r['href']})" for r in results])
            return summary
        return "No results found."
    except Exception as e:
        return "Search unavailable."

def analyze_manuscript(client, text):
    status = st.status("🔍 Analyzing Manuscript...", expanded=True)
    
    # Phase 1: Scan
    status.write("🧠 Phase 1: Critical Scan & Identifying Gaps...")
    system_prompt = (
        "You are a senior academic editor for high-impact journals like 'Medical Teacher' and 'BMC Medical Education'. "
        "You are critical, precise, and constructive."
    )
    
    prompt_phase1 = f"""
    Here is a submitted manuscript:
    <manuscript>
    {text[:100000]} 
    </manuscript>

    Analyze for: Research Question, Methodology Rigor, and Alignment with HPE literature.
    OUTPUT REQUIREMENT: Identify 3 specific claims/methods needing verification.
    Format ONLY as a Python list of strings, e.g., ["latest citation for PBL", "sample size guidelines"]
    """
    
    msg1 = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt_phase1}]
    )
    
    # Parse queries
    try:
        raw_resp = msg1.content[0].text
        start = raw_resp.find('[')
        end = raw_resp.find(']') + 1
        queries = ast.literal_eval(raw_resp[start:end])
    except:
        queries = ["Health professions education research standards"]

    # Phase 2: Search
    status.write(f"🌐 Phase 2: Searching Evidence for: {queries}")
    search_context = ""
    for q in queries:
        if isinstance(q, str):
            res = search_evidence(q)
            search_context += f"Query: {q}\nResults:\n{res}\n\n"

    # Phase 3: Report
    status.write("📝 Phase 3: Drafting Expert Report...")
    final_prompt = f"""
    Manuscript analyzed. External evidence found:
    <evidence>
    {search_context}
    </evidence>

    Generate a formal Peer Review Report. Structure:
    1. **Overview & Recommendation** (Accept/Revise/Reject)
    2. **Strengths**
    3. **Major Weaknesses** (Methodology, Ethics, Analysis)
    4. **Specific Comments** (Intro, Methods, Results, Discussion)
    5. **Missing Citations/Evidence** (Use the evidence provided)
    6. **Actionable Recommendations**

    Tone: Professional, supportive, rigorous.
    """
    
    # Save context for chat
    st.session_state.chat_history.append({"role": "user", "content": prompt_phase1})
    st.session_state.chat_history.append({"role": "assistant", "content": raw_resp})
    st.session_state.chat_history.append({"role": "user", "content": final_prompt})

    final_msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4000,
        system=system_prompt,
        messages=st.session_state.chat_history
    )
    
    report_text = final_msg.content[0].text
    
    # Save final response to history
    st.session_state.chat_history.append({"role": "assistant", "content": report_text})
    
    status.update(label="✅ Analysis Complete!", state="complete", expanded=False)
    return report_text

# --- Main App Logic ---

st.title("📄 AI Scientific Reviewer")
st.caption("Powered by Claude 3 Haiku & DuckDuckGo Search")

# 1. File Upload & Processing
if uploaded_file and not st.session_state.full_text:
    text = get_pdf_text(uploaded_file)
    if text:
        st.session_state.full_text = text
        st.success(f"PDF Loaded: {len(text)} characters.")

# 2. Run Analysis Button
if st.session_state.full_text and not st.session_state.analysis_report:
    if st.button("🚀 Start Expert Analysis"):
        report = analyze_manuscript(client, st.session_state.full_text)
        st.session_state.analysis_report = report
        st.rerun()

# 3. Display Report & Chat
if st.session_state.analysis_report:
    tab1, tab2 = st.tabs(["📝 Review Report", "💬 Chat with Manuscript"])
    
    with tab1:
        st.markdown(st.session_state.analysis_report)
        st.download_button(
            label="Download Report",
            data=st.session_state.analysis_report,
            file_name="Review_Report.md",
            mime="text/markdown"
        )
    
    with tab2:
        st.markdown("### Ask follow-up questions about the paper")
        
        # Display chat history (filtering out the hidden system logic for cleaner view)
        for msg in st.session_state.chat_history:
            # We skip the very long prompt injections and large responses to keep chat clean
            if len(msg['content']) < 2000:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        # Simple chat interface
        if prompt := st.chat_input("Ask about methodology, stats, or specific sections..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                # Create the stream
                stream = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1024,
                    messages=st.session_state.chat_history,
                    stream=True
                )
                
                # Generator function to pull ONLY text from the stream
                def text_generator():
                    for event in stream:
                        if event.type == "content_block_delta":
                            yield event.delta.text

                response = st.write_stream(text_generator)
            
            st.session_state.chat_history.append({"role": "assistant", "content": response})

else:
    if not uploaded_file:
        st.info("👈 Upload a PDF manuscript in the sidebar to begin.")
