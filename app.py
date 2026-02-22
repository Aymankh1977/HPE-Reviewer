import streamlit as st
import os
import ast
from anthropic import Anthropic
from pypdf import PdfReader
from duckduckgo_search import DDGS

# --- Page Config ---
st.set_page_config(
    page_title="HPE Expert Reviewer",
    page_icon="🧬",
    layout="wide"
)

# --- SECURE KEY HANDLING ---
# Try to get key from Streamlit Secrets (Cloud) or Environment (Local)
try:
    if "ANTHROPIC_API_KEY" in st.secrets:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY")
except FileNotFoundError:
    api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    st.error("❌ Configuration Error: ANTHROPIC_API_KEY is missing from Secrets.")
    st.stop()

client = Anthropic(api_key=api_key)

# --- Session State ---
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
    
    # NO API KEY INPUT HERE ANYMORE
    
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
    
    try:
        raw_resp = msg1.content[0].text
        start = raw_resp.find('[')
        end = raw_resp.find(']') + 1
        queries = ast.literal_eval(raw_resp[start:end])
    except:
        queries = ["Health professions education research standards"]

    status.write(f"🌐 Phase 2: Searching Evidence for: {queries}")
    search_context = ""
    for q in queries:
        if isinstance(q, str):
            res = search_evidence(q)
            search_context += f"Query: {q}\nResults:\n{res}\n\n"

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
    """
    
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
    st.session_state.chat_history.append({"role": "assistant", "content": report_text})
    
    status.update(label="✅ Analysis Complete!", state="complete", expanded=False)
    return report_text

# --- Main Interface ---
st.title("📄 AI Scientific Reviewer")
st.caption("Powered by Claude 3 Haiku & DuckDuckGo Search")

if uploaded_file and not st.session_state.full_text:
    text = get_pdf_text(uploaded_file)
    if text:
        st.session_state.full_text = text
        st.success(f"PDF Loaded: {len(text)} characters.")

if st.session_state.full_text and not st.session_state.analysis_report:
    if st.button("🚀 Start Expert Analysis"):
        report = analyze_manuscript(client, st.session_state.full_text)
        st.session_state.analysis_report = report
        st.rerun()

if st.session_state.analysis_report:
    tab1, tab2 = st.tabs(["📝 Review Report", "💬 Chat with Manuscript"])
    
    with tab1:
        st.markdown(st.session_state.analysis_report)
        st.download_button("Download Report", st.session_state.analysis_report, "Review_Report.md")
    
    with tab2:
        st.markdown("### Ask follow-up questions")
        for msg in st.session_state.chat_history:
            if len(msg['content']) < 2000:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        if prompt := st.chat_input("Ask about the paper..."):
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
                def text_generator():
                    for event in stream:
                        if event.type == "content_block_delta":
                            yield event.delta.text
                response = st.write_stream(text_generator)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
else:
    if not uploaded_file:
        st.info("👈 Upload a PDF manuscript in the sidebar to begin.")