import streamlit as st
import os
import requests
from anthropic import Anthropic
from pypdf import PdfReader
from duckduckgo_search import DDGS

# --- CONFIGURATION ---
st.set_page_config(page_title="HPE Expert Reviewer V4 (Pure Logic)", page_icon="🧠", layout="wide")

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

# --- TOOL FUNCTIONS (For Chat Only) ---
def search_pubmed(query):
    """Searches PubMed (Available only to Chat)"""
    try:
        # 1. Search IDs
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        url = f"{base}/esearch.fcgi?db=pubmed&term={query}&retmode=json&retmax=3"
        data = requests.get(url).json()
        ids = data.get("esearchresult", {}).get("idlist", [])
        
        if not ids: return "No results found in PubMed."
        
        # 2. Get Details
        ids_str = ",".join(ids)
        sum_url = f"{base}/esummary.fcgi?db=pubmed&id={ids_str}&retmode=json"
        res = requests.get(sum_url).json()
        
        output = []
        for uid in ids:
            item = res.get("result", {}).get(uid, {})
            output.append(f"- {item.get('title')} ({item.get('source')}, {item.get('pubdate')})")
        return "\n".join(output)
    except: return "PubMed Error."

def search_web(query):
    """Searches Web (Available only to Chat)"""
    try:
        results = DDGS().text(query, max_results=3)
        return "\n".join([f"- {r['title']}: {r['body']}" for r in results]) if results else "No results."
    except: return "Web Search Error."

# --- CORE LOGIC (THE V1 "SILENT CRITIC") ---
def run_v1_analysis(text):
    """
    This is the EXACT logic from Version 1. 
    NO SEARCHING. NO TOOLS. PURE TEXT ANALYSIS.
    """
    system_prompt = (
        "You are a Senior Academic Editor for high-impact journals like 'Medical Teacher', 'BMC Medical Education', and 'JDE'. "
        "You are NOT an assistant. You are a CRITIC. "
        "Your goal is to identify flaws in Logic, Methodology, and Educational Impact. "
        "You adhere strictly to guidelines: CONSORT (for trials), SRQR (for qualitative), STROBE (for observational). "
        "You look for the 'Golden Thread' (Alignment of Gap -> Question -> Methods -> Results)."
    )
    
    user_prompt = f"""
    Here is a submitted manuscript:
    <manuscript>
    {text[:130000]}
    </manuscript>

    Produce a **Strict Peer Review Report**. 
    Do not summarize the paper. Critique it.
    
    REQUIRED SECTIONS:
    
    1. **Executive Decision**: (Accept, Minor Revisions, Major Revisions, Reject).
    2. **The "Golden Thread" Analysis**: 
       - Does the Research Question directly address the Gap identified in the Intro?
       - Do the Methods actually answer the Research Question?
       - Does the Discussion link back to the Gap? (Point out any disjointed logic).
    
    3. **Methodological Rigor**:
       - Critique the Sample Size (is it justified?).
       - Critique the Analysis (is it appropriate?).
       - Critique the Ethics/Reflexivity.
    
    4. **Major Weaknesses (The 'Fatal Flaws')**:
       - List the 3 most critical issues that might lead to rejection.
       
    5. **Reference Check (Hallucination Scan)**:
       - Identify citations that look suspicious, outdated (older than 5-10 years), or irrelevant to the claim.
    
    6. **Actionable Recommendations**:
       - Concrete steps to fix the manuscript.

    Tone: Professional, Rigorous, Uncompromising.
    """
    
    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return msg.content[0].text

# --- UI LAYOUT ---
with st.sidebar:
    st.title("🧠 HPE Expert V4")
    st.markdown("**Mode:** Pure Critical Analysis (No Search Interference)")
    uploaded_file = st.file_uploader("Upload Manuscript (PDF)", type="pdf")
    
    if st.button("Clear / Reset"):
        st.session_state.clear()
        st.rerun()

# --- MAIN APP ---
if uploaded_file and not st.session_state.full_text:
    try:
        reader = PdfReader(uploaded_file)
        text = "".join([p.extract_text() for p in reader.pages])
        st.session_state.full_text = text
        st.success(f"Manuscript Loaded: {len(text)} chars.")
    except: st.error("Error reading PDF.")

# --- THE "ANALYZE" BUTTON (NO SEARCH ALLOWED HERE) ---
if st.session_state.full_text and not st.session_state.critique:
    if st.button("🚀 Run Deep Critical Review (V1 Logic)"):
        with st.spinner("🧠 Reading deeply... Analyzing logic flow... Applying CONSORT/SRQR criteria... (No internet distractions)"):
            # Call the pure V1 function
            report = run_v1_analysis(st.session_state.full_text)
            st.session_state.critique = report
            
            # Save to chat history for context
            st.session_state.chat_history.append({"role": "assistant", "content": f"I have generated the Critical Review Report based on the text provided.\n\n{report}"})
            st.rerun()

# --- RESULTS DISPLAY ---
if st.session_state.critique:
    tab1, tab2 = st.tabs(["📝 Critical Report", "💬 Intelligent Chat (With Search)"])
    
    with tab1:
        st.info("This report was generated using pure logical analysis (V1 Style). It did not search the web, ensuring maximum focus on the text structure.")
        st.markdown(st.session_state.critique)
        st.download_button("Download Report", st.session_state.critique, "Review.md")
        
    with tab2:
        st.success("💡 **Super Power Enabled:** The chat *can* search PubMed and the Web if you ask it to.")
        
        # Display History
        for msg in st.session_state.chat_history:
             if msg.get("role") != "system" and len(msg.get("content")) < 2000:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        if prompt := st.chat_input("Ex: 'Find citations for the claim in paragraph 2' or 'Rewrite the intro'"):
            st.chat_message("user").markdown(prompt)
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            with st.chat_message("assistant"):
                # 1. TOOL DECISION LAYER
                # We ask a tiny, fast model to decide if we need search tools.
                decision_prompt = f"User: '{prompt}'. Does this require searching PubMed or the Web? Answer YES or NO."
                decision = client.messages.create(
                    model="claude-3-haiku-20240307", max_tokens=10, 
                    messages=[{"role": "user", "content": decision_prompt}]
                ).content[0].text

                context_add = ""
                if "YES" in decision.upper():
                    with st.status("🔍 Searching External Databases...", expanded=True) as s:
                        pm_res = search_pubmed(prompt)
                        web_res = search_web(prompt)
                        s.write(f"PubMed found: {len(pm_res)} items")
                        s.write(f"Web found: {len(web_res)} items")
                        context_add = f"\n[SYSTEM INJECTED EVIDENCE]:\nPubMed: {pm_res}\nWeb: {web_res}\n"
                        s.update(label="Evidence Gathered", state="complete", expanded=False)

                # 2. FINAL ANSWER GENERATION
                # We feed the manuscript + critique + (optional) evidence to the chat
                system_instruction = (
                    "You are an expert Research Assistant. "
                    "You have the manuscript and the critical review report in your context. "
                    "Use the Evidence provided (if any) to answer the user's request. "
                    "If asked to rewrite, use high-impact academic style."
                )
                
                # Construct message payload
                messages = [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"Manuscript Context: {st.session_state.full_text[:30000]}..."},
                    {"role": "assistant", "content": st.session_state.critique} # The AI remembers its own critique
                ]
                
                # Add recent history
                for m in st.session_state.chat_history[-4:]:
                    messages.append(m)
                
                # Add current prompt + evidence
                messages.append({"role": "user", "content": prompt + context_add})

                stream = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=2000,
                    messages=messages,
                    stream=True
                )
                response = st.write_stream(chunk.delta.text for chunk in stream if chunk.type == "content_block_delta")
                
            st.session_state.chat_history.append({"role": "assistant", "content": response})