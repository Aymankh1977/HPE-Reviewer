import streamlit as st
import os
import ast
import requests
import re
from anthropic import Anthropic
from pypdf import PdfReader
from duckduckgo_search import DDGS
import xml.etree.ElementTree as ET

# --- CONFIGURATION ---
st.set_page_config(page_title="HPE Expert Reviewer Pro", page_icon="🧬", layout="wide")

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
if "analysis_report" not in st.session_state: st.session_state.analysis_report = ""

# --- ADVANCED TOOLS ---

def search_pubmed(query, max_results=3):
    """Searches PubMed directly for medical/HPE literature."""
    try:
        # 1. Search for IDs
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        search_url = f"{base_url}/esearch.fcgi?db=pubmed&term={query}&retmode=json&retmax={max_results}"
        resp = requests.get(search_url).json()
        ids = resp.get("esearchresult", {}).get("idlist", [])
        
        if not ids:
            return "No PubMed articles found."

        # 2. Get Summaries
        ids_str = ",".join(ids)
        summary_url = f"{base_url}/esummary.fcgi?db=pubmed&id={ids_str}&retmode=json"
        summary_resp = requests.get(summary_url).json()
        
        results = []
        for uid in ids:
            item = summary_resp.get("result", {}).get(uid, {})
            title = item.get("title", "No title")
            source = item.get("source", "Unknown Source")
            pubdate = item.get("pubdate", "No date")
            results.append(f"- **{title}** ({source}, {pubdate})")
            
        return "\n".join(results)
    except Exception as e:
        return f"PubMed Error: {e}"

def search_web(query):
    """Fallback to DuckDuckGo for general queries."""
    try:
        results = DDGS().text(query, max_results=3)
        if results:
            return "\n".join([f"- {r['title']}: {r['body']} (Source: {r['href']})" for r in results])
        return "No web results found."
    except:
        return "Web search unavailable."

def check_citation_validity(citation_text):
    """Uses PubMed to check if a specific citation string likely exists."""
    # Strip year and brackets to get a clean query
    clean_query = re.sub(r'[^\w\s]', '', citation_text)[:100] # Limit length
    return search_pubmed(clean_query, max_results=1)

def analyze_manuscript(text):
    status = st.status("🔍 Starting Deep Analysis...", expanded=True)
    
    # --- PHASE 1: Structure & Logic Scan ---
    status.write("🧠 Phase 1: Analyzing Logic, Flow, and Manuscript Structure...")
    
    system_prompt = (
        "You are an expert reviewer for top-tier journals like 'Medical Teacher'. "
        "You focus on 'Constructive Alignment' and the 'Golden Thread' of logic. "
        "You are skeptical of claims without evidence."
    )

    prompt_scan = f"""
    Analyze this manuscript (Text limited to 100k chars):
    <manuscript>
    {text[:100000]}
    </manuscript>

    Task 1: Evaluate the LOGIC and STRUCTURE. 
    - Does the Introduction end with a clear gap?
    - Do the Methods directly answer the Research Question?
    - Are the Results presented without interpretation?
    - Does the Discussion link back to the gap?

    Task 2: Identify 3 specific references or claims that look suspicious or outdated.
    
    Output Format: ONLY a Python list of strings for Task 2, e.g., ["Effectiveness of PBL 2005", "Smith et al 2019 data"]
    """
    
    msg1 = client.messages.create(
        model="claude-3-haiku-20240307", 
        max_tokens=1024, 
        system=system_prompt,
        messages=[{"role": "user", "content": prompt_scan}]
    )
    
    # Extract Queries for Verification
    try:
        raw_text = msg1.content[0].text
        start = raw_text.find('[')
        end = raw_text.find(']') + 1
        queries = ast.literal_eval(raw_text[start:end])
    except:
        queries = ["Medical education research trends"]

    # --- PHASE 2: Multi-Source Verification ---
    status.write(f"🌐 Phase 2: Verifying claims via PubMed & Web ({len(queries)} checks)...")
    
    evidence_block = ""
    for q in queries:
        pubmed_res = search_pubmed(q)
        web_res = search_web(q)
        evidence_block += f"### Checking Claim/Ref: '{q}'\n**PubMed found:**\n{pubmed_res}\n**Web found:**\n{web_res}\n\n"

    # --- PHASE 3: Similar Papers ---
    status.write("📚 Phase 3: finding similar recent publications in HPE...")
    # Generate a keyword search based on the first query extracted
    similar_papers = search_pubmed(f"{queries[0]} review", max_results=4)

    # --- PHASE 4: Final Report ---
    status.write("📝 Phase 4: Compiling Expert Reviewer Report...")
    
    final_prompt = f"""
    You are the Editor-in-Chief. Write a robust Peer Review Report.
    
    INPUT DATA:
    1. Manuscript Text (already provided in context).
    2. Verification Evidence: 
    {evidence_block}
    3. Similar/Recent Papers found in PubMed:
    {similar_papers}

    REPORT SECTIONS:
    1. **Executive Summary & Decision**: (Accept, Minor, Major, Reject).
    2. **Structure & Logic Check**: 
       - Critique the "Golden Thread" (Coherence from Intro to Conclusion).
       - Comment on the "Gap" identification.
    3. **Methodological Rigor**: 
       - Check against CONSORT (if quantitative) or SRQR (if qualitative).
    4. **Reference Quality & Validity**:
       - Discuss if citations are current (last 5 years).
       - Note any potential "hallucinated" or incorrect citations based on the evidence check.
    5. **Similar Work**: 
       - Mention the similar papers found ({similar_papers}) and how this manuscript compares.
    6. **Specific Recommendations**: Bullet points.

    Tone: Strict, Academic, Helpful.
    """
    
    # Maintain context
    st.session_state.chat_history.append({"role": "user", "content": prompt_scan})
    st.session_state.chat_history.append({"role": "assistant", "content": raw_text})
    st.session_state.chat_history.append({"role": "user", "content": final_prompt})

    final_msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4000,
        system=system_prompt,
        messages=st.session_state.chat_history
    )
    
    report = final_msg.content[0].text
    st.session_state.chat_history.append({"role": "assistant", "content": report})
    
    status.update(label="Analysis Complete!", state="complete", expanded=False)
    return report

# --- SIDEBAR ---
with st.sidebar:
    st.title("🧬 HPE Reviewer Pro")
    st.markdown("Connected to **PubMed** & **Web**")
    
    uploaded_file = st.file_uploader("Upload Manuscript (PDF)", type="pdf")
    if st.button("Reset System"):
        st.session_state.chat_history = []
        st.session_state.full_text = ""
        st.session_state.analysis_report = ""
        st.rerun()

# --- MAIN PAGE ---
if uploaded_file and not st.session_state.full_text:
    try:
        reader = PdfReader(uploaded_file)
        text = "".join([p.extract_text() for p in reader.pages])
        st.session_state.full_text = text
        st.success(f"Manuscript Loaded: {len(text)} chars")
    except Exception as e:
        st.error(f"Error reading PDF: {e}")

if st.session_state.full_text and not st.session_state.analysis_report:
    if st.button("🚀 Start Deep Analysis"):
        st.session_state.analysis_report = analyze_manuscript(st.session_state.full_text)
        st.rerun()

if st.session_state.analysis_report:
    tab1, tab2 = st.tabs(["📝 Expert Report", "💬 Internet-Enabled Chat"])
    
    with tab1:
        st.markdown(st.session_state.analysis_report)
        st.download_button("Download Report", st.session_state.analysis_report, "Review.md")
    
    with tab2:
        st.info("💡 The chat now has access to PubMed and the Web. Ask it to 'check this reference' or 'find similar papers'.")
        
        # Display chat (filtered)
        for msg in st.session_state.chat_history:
            if len(msg['content']) < 3000: # Hide massive prompts
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
        
        if prompt := st.chat_input("Ask about the paper or search for info..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            st.chat_message("user").markdown(prompt)
            
            # --- INTELLIGENT CHAT AGENT ---
            with st.chat_message("assistant"):
                # 1. Decide if we need to search
                tool_check_prompt = f"User asked: '{prompt}'. Should I search PubMed or the Web? Answer YES or NO."
                check = client.messages.create(
                    model="claude-3-haiku-20240307", max_tokens=10, 
                    messages=[{"role": "user", "content": tool_check_prompt}]
                ).content[0].text
                
                context_add = ""
                if "YES" in check.upper():
                    with st.spinner("Searching external databases..."):
                        pm_res = search_pubmed(prompt)
                        web_res = search_web(prompt)
                        context_add = f"\n[SYSTEM: I performed a live search based on the user question.]\nPubMed Results: {pm_res}\nWeb Results: {web_res}\n"
                
                # 2. Generate Answer
                final_chat_prompt = prompt + context_add
                
                # We don't append the context to history permanently to save tokens, just for this turn
                temp_messages = st.session_state.chat_history.copy()
                if context_add:
                    temp_messages[-1]['content'] = final_chat_prompt

                stream = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1024,
                    messages=temp_messages,
                    stream=True
                )
                response = st.write_stream(chunk.delta.text for chunk in stream if chunk.type == "content_block_delta")
                
            st.session_state.chat_history.append({"role": "assistant", "content": response})