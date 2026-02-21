import streamlit as st
import os
import ast
import requests
import re
from anthropic import Anthropic
from pypdf import PdfReader
from duckduckgo_search import DDGS

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
if "evidence_context" not in st.session_state: st.session_state.evidence_context = ""

# --- SEARCH TOOLS ---

def search_pubmed(query, max_results=3):
    """Searches PubMed directly for medical/HPE literature."""
    try:
        # Search for IDs
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        search_url = f"{base_url}/esearch.fcgi?db=pubmed&term={query}&retmode=json&retmax={max_results}"
        resp = requests.get(search_url).json()
        ids = resp.get("esearchresult", {}).get("idlist", [])
        
        if not ids: return "No PubMed articles found."

        # Get Summaries
        ids_str = ",".join(ids)
        summary_url = f"{base_url}/esummary.fcgi?db=pubmed&id={ids_str}&retmode=json"
        summary_resp = requests.get(summary_url).json()
        
        results = []
        for uid in ids:
            item = summary_resp.get("result", {}).get(uid, {})
            title = item.get("title", "No title")
            source = item.get("source", "Unknown Source")
            pubdate = item.get("pubdate", "No date")
            results.append(f"- {title} ({source}, {pubdate})")
            
        return "\n".join(results)
    except Exception as e:
        return f"PubMed Error: {e}"

def search_web(query):
    """Fallback to DuckDuckGo."""
    try:
        results = DDGS().text(query, max_results=3)
        if results:
            return "\n".join([f"- {r['title']}: {r['body']} (Source: {r['href']})" for r in results])
        return "No web results found."
    except:
        return "Web search unavailable."

# --- CORE ANALYSIS LOGIC ---

def analyze_manuscript_logic(text):
    """
    STAGE 1: THE DEEP READ.
    Focus: Internal logic, methodology, CONSORT/SRQR adherence, flow.
    NO searching here. Just pure critical analysis.
    """
    system_prompt = (
        "You are a senior, ruthless academic editor for 'Medical Teacher' and 'BMC Medical Education'. "
        "You do not summarize. You CRITIQUE. "
        "You focus on the 'Golden Thread' (alignment of Question -> Methods -> Results). "
        "You identify methodological flaws, statistical errors, and gaps in logic."
    )
    
    user_prompt = f"""
    Here is the manuscript text (truncated to fit context if needed):
    <manuscript>
    {text[:120000]}
    </manuscript>

    PART 1: CRITICAL ANALYSIS
    Perform a deep review. Focus on:
    1. **The Gap**: Is it explicitly defined? Or is the intro generic?
    2. **Methodology**: Is it reproducible? Does it match the research question? (Check Sample Size, Ethics, Analysis).
    3. **Results**: Are they over-interpreted? Do they actually support the conclusion?
    4. **The "Golden Thread"**: Does the logic flow seamlessly or is it disjointed?

    PART 2: IDENTIFY VERIFICATION NEEDS
    Identify 3-4 specific claims, references, or lack of similar studies that I need to verify externally.
    
    OUTPUT FORMAT:
    Provide a Python list of strings at the very end for verification, e.g., ["Citation check for Smith 2019", "Similar studies on VR in anatomy"]
    """

    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return message.content[0].text, user_prompt

def generate_final_report(initial_critique, evidence, original_text):
    """
    STAGE 2: THE SYNTHESIS.
    Combines the deep critique with the external evidence found.
    """
    system_prompt = "You are the Editor-in-Chief. Compile the final decision letter."
    
    final_prompt = f"""
    I have performed an initial critical analysis of the manuscript.
    
    <initial_critique>
    {initial_critique}
    </initial_critique>

    <external_evidence_found>
    {evidence}
    </external_evidence_found>

    Now, rewrite the Final Peer Review Report. 
    1. Integrate the external evidence into the critique (e.g., "The authors claim X is novel, but PubMed search reveals...").
    2. Be specific about the flow of information and writing logic.
    3. Provide a clear Recommendation (Accept/Reject/Revise).
    4. List Actionable Changes.
    
    Style: rigorous, high-impact journal standard.
    """
    
    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": final_prompt}]
    )
    return message.content[0].text

# --- SIDEBAR ---
with st.sidebar:
    st.title("🧬 HPE Reviewer Pro")
    st.caption("v2.1: Deep Logic + PubMed")
    uploaded_file = st.file_uploader("Upload Manuscript (PDF)", type="pdf")
    if st.button("Reset"):
        st.session_state.clear()
        st.rerun()

# --- MAIN UI ---
if uploaded_file and not st.session_state.full_text:
    try:
        reader = PdfReader(uploaded_file)
        text = "".join([p.extract_text() for p in reader.pages])
        st.session_state.full_text = text
        st.success(f"Manuscript Loaded: {len(text)} chars")
    except Exception as e:
        st.error(f"Error reading PDF: {e}")

if st.session_state.full_text and not st.session_state.analysis_report:
    if st.button("🚀 Start Critical Analysis"):
        status = st.status("🔍 Performing Expert Review...", expanded=True)
        
        # 1. Deep Read (Internal Logic)
        status.write("🧠 Phase 1: Deep Reading & Logic Extraction (No Internet)...")
        critique_draft, prompt_used = analyze_manuscript_logic(st.session_state.full_text)
        
        # 2. Extract Queries
        try:
            start = critique_draft.find('[')
            end = critique_draft.rfind(']') + 1
            queries = ast.literal_eval(critique_draft[start:end])
        except:
            queries = ["Medical education research methodology"]
        
        # 3. Search Evidence
        status.write(f"🌐 Phase 2: Verifying claims via PubMed/Web ({len(queries)} items)...")
        evidence_block = ""
        for q in queries:
            if isinstance(q, str):
                pm_res = search_pubmed(q)
                web_res = search_web(q)
                evidence_block += f"### Checking: '{q}'\n- PubMed: {pm_res}\n- Web: {web_res}\n\n"
        
        st.session_state.evidence_context = evidence_block
        
        # 4. Final Synthesis
        status.write("📝 Phase 3: Synthesizing Final Expert Report...")
        final_report = generate_final_report(critique_draft, evidence_block, st.session_state.full_text)
        
        # Save to state
        st.session_state.analysis_report = final_report
        st.session_state.chat_history.append({"role": "user", "content": prompt_used}) # Context
        st.session_state.chat_history.append({"role": "assistant", "content": critique_draft}) # Context
        st.session_state.chat_history.append({"role": "assistant", "content": final_report}) # Result
        
        status.update(label="Review Complete", state="complete", expanded=False)
        st.rerun()

if st.session_state.analysis_report:
    tab1, tab2 = st.tabs(["📝 Critical Review", "💬 Expert Chat"])
    
    with tab1:
        st.markdown(st.session_state.analysis_report)
        st.download_button("Download Review", st.session_state.analysis_report, "Review.md")
        with st.expander("View Evidence Gathered"):
            st.code(st.session_state.evidence_context)
            
    with tab2:
        st.info("The Chat is now aware of the full manuscript logic + external evidence found.")
        
        for msg in st.session_state.chat_history:
            if msg['role'] == 'user' and len(msg['content']) < 500: # Show only user chats
                st.chat_message("user").markdown(msg["content"])
            elif msg['role'] == 'assistant' and len(msg['content']) < 2000: # Show short answers
                 # We skip the massive report to keep chat clean
                 st.chat_message("assistant").markdown(msg["content"])

        if prompt := st.chat_input("Ask about logic, flow, or specific citations..."):
            st.chat_message("user").markdown(prompt)
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            with st.chat_message("assistant"):
                # Decide if we need NEW evidence
                check_prompt = f"User asked: '{prompt}'. Should I search PubMed again? Answer YES/NO."
                check = client.messages.create(model="claude-3-haiku-20240307", max_tokens=10, messages=[{"role": "user", "content": check_prompt}]).content[0].text
                
                context_add = ""
                if "YES" in check.upper():
                    with st.spinner("Checking databases..."):
                        pm = search_pubmed(prompt)
                        context_add = f"\n[NEW SEARCH RESULTS]: {pm}\n"
                
                # Chat with full context
                messages_for_api = st.session_state.chat_history.copy()
                if context_add:
                    messages_for_api.append({"role": "user", "content": f"(Context update: {context_add})"})

                stream = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1024,
                    messages=messages_for_api,
                    stream=True
                )
                response = st.write_stream(chunk.delta.text for chunk in stream if chunk.type == "content_block_delta")
                st.session_state.chat_history.append({"role": "assistant", "content": response})