import streamlit as st
import os
import requests
from anthropic import Anthropic
from pypdf import PdfReader
from duckduckgo_search import DDGS

# --- CONFIGURATION ---
st.set_page_config(page_title="HPE Expert Reviewer V3 (Strict)", page_icon="⚖️", layout="wide")

# --- SECURE KEY HANDLING ---
try:
    if "ANTHROPIC_API_KEY" in st.secrets:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY")
except FileNotFoundError:
    api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    st.error("🚨 API Key missing! Please add ANTHROPIC_API_KEY to Streamlit Secrets.")
    st.stop()

client = Anthropic(api_key=api_key)

# --- SESSION STATE ---
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "full_text" not in st.session_state: st.session_state.full_text = ""
if "critique" not in st.session_state: st.session_state.critique = ""
if "mode" not in st.session_state: st.session_state.mode = "Analyze"

# --- TOOLS ---
def search_pubmed(query):
    """Specific tool for medical literature"""
    try:
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query}&retmode=json&retmax=3"
        ids = requests.get(url).json().get("esearchresult", {}).get("idlist", [])
        if not ids: return "No specific papers found."
        
        summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={','.join(ids)}&retmode=json"
        data = requests.get(summary_url).json().get("result", {})
        results = [f"- {data[uid].get('title')} ({data[uid].get('source')}, {data[uid].get('pubdate')})" for uid in ids if uid != 'uids']
        return "\n".join(results)
    except: return "PubMed lookup failed."

# --- CORE LOGIC (THE V1 BRAIN) ---
def deep_critical_analysis(text):
    """
    This function uses the STRICT V1 PROMPT. 
    It focuses purely on logic, methodology, and flow. No distractions.
    """
    system_prompt = (
        "You are a Senior Editor for 'Medical Teacher' and 'BMC Medical Education'. "
        "Your job is NOT to be nice. Your job is to ensure scientific rigor. "
        "You adhere to CONSORT (trials), SRQR (qualitative), and STROBE (observational) guidelines. "
        "You focus on the 'Golden Thread': alignment of Gap -> Question -> Methods -> Results -> Discussion."
    )
    
    user_prompt = f"""
    Here is a submitted manuscript:
    <manuscript>
    {text[:120000]}
    </manuscript>

    Write a Critical Peer Review Report. Do not summarize the paper. Critique it.
    
    Your Report must have these exact sections:
    
    1. **The 'Golden Thread' Analysis**: 
       - Does the Research Question directly address the Gap identified in the Intro?
       - Do the Methods actually answer the Research Question?
       - Does the Discussion link back to the Gap? (Point out any disjointed logic).
    
    2. **Methodological Rigor**:
       - Critique the Sample Size (is it justified?).
       - Critique the Analysis (is it appropriate?).
       - Critique the Ethics/Reflexivity.
    
    3. **HPE Context**:
       - Is this relevant to Health Professions Education? 
       - Does it cite recent (last 5 years) literature?
    
    4. **The Verdict**:
       - List 3 Major Flaws that must be fixed.
       - List 3 Minor Flaws.
    
    5. **Action Plan**:
       - Concrete steps to improve the manuscript before submission.
    """
    
    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return message.content[0].text

# --- THE CO-AUTHOR BRAIN (CHAT) ---
def chat_with_coauthor(prompt):
    """
    The chat is now an 'Improver'. It knows the critique and helps you fix the paper.
    It can search PubMed if you ask.
    """
    # Check if user wants to search
    tool_use = False
    search_context = ""
    
    if "find" in prompt.lower() or "search" in prompt.lower() or "reference" in prompt.lower():
        tool_use = True
        with st.spinner("Searching PubMed/Web for evidence..."):
            pubmed_res = search_pubmed(prompt)
            search_context = f"\n[SYSTEM: External Evidence Found: {pubmed_res}]\n"

    # Contextual Prompt
    system_prompt = (
        "You are a helpful Co-Author and Research Assistant. "
        "You have read the manuscript and the Critical Review Report generated earlier. "
        "Your goal is to help the user FIX the issues identified in the report. "
        "If the user asks to rewrite a section, rewrite it to be academic, precise, and high-impact."
    )
    
    # Inject the critique into the memory so the chat knows what to fix
    context = f"""
    <current_manuscript_context>
    {st.session_state.full_text[:30000]}... (truncated)
    </current_manuscript_context>

    <critical_review_report>
    {st.session_state.critique}
    </critical_review_report>
    
    {search_context}
    """
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context: {context}\n\nUser Question: {prompt}"}
    ]
    
    # We append previous chat history (excluding the massive context block to save tokens)
    for msg in st.session_state.chat_history[-4:]: # Keep last 4 turns
        if msg["role"] != "system":
            messages.append(msg)

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=2000,
        messages=messages
    )
    return response.content[0].text

# --- UI LAYOUT ---
with st.sidebar:
    st.title("⚖️ HPE Expert V3")
    st.markdown("Strict Logic Analysis + Co-Author Chat")
    uploaded_file = st.file_uploader("Upload Manuscript (PDF)", type="pdf")
    if st.button("Reset Analysis"):
        st.session_state.clear()
        st.rerun()

# --- MAIN APP ---
if uploaded_file and not st.session_state.full_text:
    try:
        reader = PdfReader(uploaded_file)
        text = "".join([p.extract_text() for p in reader.pages])
        st.session_state.full_text = text
        st.success(f"Loaded {len(text)} characters. Ready for deep analysis.")
    except: st.error("Error reading PDF.")

if st.session_state.full_text and not st.session_state.critique:
    if st.button("🚀 Run Deep Critical Analysis (V1 Logic)"):
        with st.spinner("🧠 Performing deep logical stress-test (no internet distraction)..."):
            report = deep_critical_analysis(st.session_state.full_text)
            st.session_state.critique = report
            st.rerun()

if st.session_state.critique:
    tab1, tab2 = st.tabs(["📝 Critical Report", "✍️ Co-Author Chat (Improve It)"])
    
    with tab1:
        st.warning("This report focuses on Logic, Flow, and Methodology Rigor.")
        st.markdown(st.session_state.critique)
        st.download_button("Download Report", st.session_state.critique, "Review.md")
        
    with tab2:
        st.info("💡 **Feature:** Ask me to *rewrite* the Introduction, *find* citations for a claim, or *fix* the logic gaps found in the report.")
        
        # Show chat interface
        for msg in st.session_state.chat_history:
             if msg.get("role") != "system":
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        if prompt := st.chat_input("Ex: 'Rewrite the abstract to address the logic gap' or 'Find references for PBL'"):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            
            with st.chat_message("assistant"):
                response = chat_with_coauthor(prompt)
                st.markdown(response)
            
            st.session_state.chat_history.append({"role": "assistant", "content": response})