import streamlit as st
import os
from anthropic import Anthropic
from pypdf import PdfReader

# --- CONFIGURATION ---
st.set_page_config(page_title="HPE Expert Reviewer (Original Logic)", page_icon="📝", layout="wide")

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

# --- THE ORIGINAL V1 LOGIC ---
def run_v1_critical_analysis(text):
    """
    This uses the EXACT logic from the first version you liked.
    It has NO knowledge of the internet. It focuses 100% on the text structure.
    """
    
    # This is the "Ruthless Editor" prompt
    system_prompt = (
        "You are a senior academic editor for high-impact journals like 'Medical Teacher' and 'BMC Medical Education'. "
        "You are critical, precise, and constructive. "
        "You adhere to guidelines like CONSORT (trials), SRQR (qualitative), "
        "and focus on educational impact (Kirkpatrick levels)."
    )

    user_prompt = f"""
    Here is a submitted manuscript:
    <manuscript>
    {text[:120000]} 
    </manuscript>
    (Note: Text truncated if too long, strictly analyze provided text).

    Please perform a critical analysis focusing on:
    1. Clarity of the Research Question.
    2. Methodology rigor (Sample size, ethics, statistical/qualitative analysis).
    3. Alignment with current Health Professions Education (HPE) literature.
    
    Generate a formal Peer Review Report. Use the following structure:
    
    1. **Overview & General Recommendation**: (Accept, Minor Revisions, Major Revisions, Reject).
    2. **Strengths**: What is novel or well-done?
    3. **Major Weaknesses**: Critical flaws in methodology, ethics, or analysis.
    4. **Specific Comments**:
       - **Introduction**: Is the gap identified? Are citations current?
       - **Methods**: Is it reproducible? Is the qualitative/quantitative approach sound?
       - **Results**: Are they clear?
       - **Discussion**: Do they overstate findings? 
    5. **Missing Citations/Evidence**: Identify gaps where the authors should have cited more evidence.
    6. **Actionable Recommendations**: Bullet points on exactly how to fix the paper.

    The tone must be professional, supportive but rigorous.
    """

    # We use a slightly higher temperature (0.3) to allow for more critical "opinion"
    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4000,
        temperature=0.3,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    
    return message.content[0].text

# --- UI LAYOUT ---
with st.sidebar:
    st.title("📝 HPE Reviewer (V1)")
    st.markdown("Restored Original Logic")
    uploaded_file = st.file_uploader("Upload Manuscript (PDF)", type="pdf")
    if st.button("Reset"):
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

# --- BUTTON: RUN ORIGINAL ANALYSIS ---
if st.session_state.full_text and not st.session_state.critique:
    if st.button("🚀 Run Critical Analysis"):
        with st.spinner("Analyzing manuscript (V1 Logic)..."):
            report = run_v1_critical_analysis(st.session_state.full_text)
            st.session_state.critique = report
            # Seed chat history with the result so the chat knows about it
            st.session_state.chat_history.append({"role": "assistant", "content": report})
            st.rerun()

# --- DISPLAY RESULTS ---
if st.session_state.critique:
    tab1, tab2 = st.tabs(["📝 Review Report", "💬 Chat"])
    
    with tab1:
        st.markdown(st.session_state.critique)
        st.download_button("Download Report", st.session_state.critique, "Review_Report.md")
        
    with tab2:
        st.info("You can ask questions about the manuscript or the review report here.")
        
        for msg in st.session_state.chat_history:
            if msg.get("role") != "system":
                 # Only show user messages and short assistant messages to keep UI clean
                 if len(msg.get("content")) < 2000:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])

        if prompt := st.chat_input("Ask about the review..."):
            st.chat_message("user").markdown(prompt)
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            with st.chat_message("assistant"):
                # We simply feed the full context (Manuscript + Review) to the chat
                # No searching tools, just pure text understanding
                messages = [
                    {"role": "system", "content": "You are a helpful research assistant. You have read the manuscript and the review report."},
                    {"role": "user", "content": f"Manuscript Context: {st.session_state.full_text[:30000]}..."},
                    {"role": "assistant", "content": st.session_state.critique}
                ]
                # Add recent conversation
                for m in st.session_state.chat_history[-4:]:
                    messages.append(m)
                
                # Add current question
                messages.append({"role": "user", "content": prompt})

                stream = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1024,
                    messages=messages,
                    stream=True
                )
                response = st.write_stream(chunk.delta.text for chunk in stream if chunk.type == "content_block_delta")
                
            st.session_state.chat_history.append({"role": "assistant", "content": response})