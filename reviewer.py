#!/usr/bin/env python3
import os, sys, json, base64, argparse
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic
from pypdf import PdfReader
from termcolor import colored

load_dotenv()
API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    print(colored("Error: ANTHROPIC_API_KEY not set.", "red"))
    sys.exit(1)
print(colored(f"API key detected: {API_KEY[:12]}...", "green"))
client = Anthropic(api_key=API_KEY)
PRIMARY_MODEL  = "claude-sonnet-4-5"
FALLBACK_MODEL = "claude-haiku-4-5-20251001"
JOURNALS = ["Medical Teacher","BMC Medical Education","Academic Medicine","Medical Education","JGME","Teaching and Learning in Medicine"]
REVIEW_CRITERIA = {
    "research_question": "Research question clarity & PICO/SPIDER framing",
    "methodology":       "Methodology rigor & reproducibility",
    "consort_srqr":      "CONSORT / SRQR / COREQ guideline adherence",
    "kirkpatrick":       "Kirkpatrick level outcomes achieved",
    "citations":         "Citation currency, completeness & in-text accuracy",
    "statistics":        "Statistical / qualitative data analysis soundness",
    "ethics":            "Ethical considerations & positionality",
    "golden_thread":     "Golden thread coherence (RQ to method to results to conclusion)",
}

class HPEReviewer:
    def __init__(self, pdf_path, journal="Medical Teacher"):
        self.pdf_path   = Path(pdf_path)
        self.journal    = journal
        self.pdf_base64 = self._encode_pdf()
        self.pdf_text   = self._extract_text()
        self.chat_history = []
        self.report = None
        print(colored(f"Loaded: {self.pdf_path.name}", "cyan"))
        print(colored(f"{len(self.pdf_text):,} chars extracted", "cyan"))
        print(colored(f"Target journal: {self.journal}", "cyan"))

    def _encode_pdf(self):
        with open(self.pdf_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")

    def _extract_text(self):
        try:
            reader = PdfReader(str(self.pdf_path))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            print(colored(f"Warning: text extraction failed ({e})", "yellow"))
            return ""

    @property
    def system_prompt(self):
        return (
            f"You are a Senior Editor and double-blind Peer Reviewer for '{self.journal}', "
            "one of the most rigorous journals in Health Professions Education. "
            "Your reviews are precise, evidence-based, and constructive. "
            "You quote exact passages from the manuscript to substantiate every criticism. "
            "You never fabricate. Apply CONSORT for RCTs, SRQR for qualitative research, COREQ for interviews. "
            "Evaluate educational outcomes through Kirkpatrick's four-level framework. "
            "Scrutinise the golden thread: RQ to methodology to results to conclusion. "
            "Identify citation gaps, outdated references, and in-text/reference-list mismatches."
        )

    def _build_prompt(self, criteria):
        criteria_block = "\n".join(f"  {i+1}. {REVIEW_CRITERIA[c]}" for i,c in enumerate(criteria))
        return f"""Perform a comprehensive peer review of this manuscript submitted to '{self.journal}'.
SELECTED REVIEW CRITERIA:\n{criteria_block}
Return ONLY a valid JSON object with exactly this schema:
{{
  "verdict": "Accept | Minor Revisions | Major Revisions | Reject",
  "overall_score": 0,
  "executive_summary": "",
  "scores": {{"novelty":0,"methodology":0,"clarity":0,"citations":0,"ethics":0}},
  "strengths": [],
  "weaknesses": [{{"section":"","issue":"","severity":"major|minor","suggestion":""}}],
  "section_comments": {{"abstract":"","introduction":"","methods":"","results":"","discussion":""}},
  "golden_thread": "",
  "kirkpatrick_level": {{"level":0,"justification":""}},
  "citation_audit": {{"missing_key_references":[],"potentially_outdated":[],"mismatches":""}},
  "actionable_recommendations": [],
  "editor_note": ""
}}"""

    def _call_pdf(self, prompt, model):
        r = client.messages.create(model=model, max_tokens=4096, system=self.system_prompt,
            messages=[{"role":"user","content":[
                {"type":"document","source":{"type":"base64","media_type":"application/pdf","data":self.pdf_base64}},
                {"type":"text","text":prompt}]}])
        return r.content[0].text

    def _call_text(self, prompt, model):
        r = client.messages.create(model=model, max_tokens=4096, system=self.system_prompt,
            messages=[{"role":"user","content":f"MANUSCRIPT:\n{self.pdf_text[:120000]}\n\n{prompt}"}])
        return r.content[0].text

    def _robust_call(self, prompt):
        for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
            try:
                print(colored(f"Trying {model} with native PDF...", "yellow"))
                raw = self._call_pdf(prompt, model)
                print(colored(f"Success ({model} native PDF)", "green"))
                return raw, f"{model} (native PDF)"
            except Exception as e:
                print(colored(f"PDF mode failed: {e} - trying text...", "yellow"))
            if self.pdf_text:
                try:
                    raw = self._call_text(prompt, model)
                    print(colored(f"Success ({model} text mode)", "green"))
                    return raw, f"{model} (text mode)"
                except Exception as e2:
                    print(colored(f"Text mode failed: {e2}", "red"))
        raise RuntimeError("All API strategies failed.")

    def _parse(self, raw):
        try:
            return json.loads(raw[raw.index("{"):raw.rindex("}")+1])
        except:
            return None

    def analyze(self, criteria=None):
        if criteria is None:
            criteria = list(REVIEW_CRITERIA.keys())
        phases = ["Phase 1: Deep document read","Phase 2: Methodology assessment","Phase 3: Citation audit","Phase 4: Generating report"]
        for p in phases:
            print(colored(f"\n--- {p} ---", "green"))
        prompt = self._build_prompt(criteria)
        raw, model_used = self._robust_call(prompt)
        report = self._parse(raw)
        self.report = report
        self.chat_history = [
            {"role":"user","content":[
                {"type":"document","source":{"type":"base64","media_type":"application/pdf","data":self.pdf_base64}},
                {"type":"text","text":"This is the manuscript we reviewed."}]},
            {"role":"assistant","content":f"Completed peer review:\n{raw}"}]
        return report, raw, model_used

    def print_report(self, report, raw):
        print(colored("\n" + "="*60, "white"))
        if report is None:
            print(raw); return
        verdict = report.get("verdict","Unknown")
        score   = report.get("overall_score","—")
        clr = "green" if "accept" in verdict.lower() and "minor" not in verdict.lower() else "yellow" if "minor" in verdict.lower() else "red"
        print(colored(f"  Verdict: {verdict}  |  Score: {score}/100", clr, attrs=["bold"]))
        print(colored(f"  {report.get('executive_summary','')}", "white"))
        for k,v in report.get("scores",{}).items():
            print(f"  {k:<14} {'█'*int(v)}{'░'*(10-int(v))}  {v}/10")
        kp = report.get("kirkpatrick_level",{})
        if kp: print(colored(f"  Kirkpatrick Level {kp.get('level','?')}: {kp.get('justification','')}", "cyan"))
        print(colored(f"\n  Golden Thread:\n  {report.get('golden_thread','')}", "magenta"))
        for s in report.get("strengths",[]): print(colored(f"  + {s}", "green"))
        for w in report.get("weaknesses",[]): print(colored(f"  {'!' if w.get('severity')=='major' else 'o'} [{w.get('severity','').upper()} - {w.get('section','')}] {w.get('issue','')}", "red" if w.get("severity")=="major" else "yellow"))
        print(colored("\n  Recommendations:", "cyan"))
        for i,r in enumerate(report.get("actionable_recommendations",[]),1): print(f"  {i}. {r}")
        ca = report.get("citation_audit",{})
        for ref in ca.get("missing_key_references",[]): print(colored(f"  Missing: {ref}", "yellow"))
        print(colored("="*60, "white"))

    def save(self, report, raw, path):
        if report is None:
            content = raw
        else:
            lines = [f"# HPE Peer Review Report",f"**Verdict:** {report.get('verdict','—')}  |  **Score:** {report.get('overall_score','—')}/100","",report.get('executive_summary',''),"","## Scores"]
            for k,v in report.get("scores",{}).items(): lines.append(f"- {k}: {v}/10")
            kp = report.get("kirkpatrick_level",{})
            if kp: lines += ["",f"## Kirkpatrick Level {kp.get('level','?')}",kp.get("justification","")]
            lines += ["","## Golden Thread",report.get("golden_thread",""),"","## Strengths"]
            for s in report.get("strengths",[]): lines.append(f"- {s}")
            lines += ["","## Weaknesses"]
            for w in report.get("weaknesses",[]): lines.append(f"- [{w.get('severity','').upper()} - {w.get('section','')}] {w.get('issue','')}\n  Suggestion: {w.get('suggestion','')}")
            lines += ["","## Section Comments"]
            for sec,comment in report.get("section_comments",{}).items(): lines += [f"### {sec.capitalize()}",comment,""]
            lines += ["","## Citation Audit"]
            ca = report.get("citation_audit",{})
            for ref in ca.get("missing_key_references",[]): lines.append(f"- Missing: {ref}")
            for ref in ca.get("potentially_outdated",[]): lines.append(f"- Outdated: {ref}")
            lines.append(f"- Mismatches: {ca.get('mismatches','None identified')}")
            lines += ["","## Actionable Recommendations"]
            for i,r in enumerate(report.get("actionable_recommendations",[]),1): lines.append(f"{i}. {r}")
            en = report.get("editor_note","")
            if en: lines += ["","## Confidential Note to Editor",f"*{en}*"]
            content = "\n".join(lines)
        with open(path,"w",encoding="utf-8") as f: f.write(content)
        print(colored(f"Report saved to: {path}", "green"))

    def chat_loop(self):
        print(colored("\n--- Interactive Chat (type exit to quit) ---", "blue"))
        suggestions = ["Expand methodology critique","Which citations are missing?","How to improve the Discussion?","Kirkpatrick level justification?","Suggest a revised Abstract"]
        for i,s in enumerate(suggestions,1): print(colored(f"  [{i}] {s}", "cyan"))
        while True:
            try: user_input = input(colored("\nYou: ", "yellow")).strip()
            except (EOFError, KeyboardInterrupt): break
            if user_input.lower() in ("exit","quit","q"): break
            if user_input.isdigit():
                idx = int(user_input)-1
                if 0 <= idx < len(suggestions): user_input = suggestions[idx]; print(colored(f"  -> {user_input}","cyan"))
            if not user_input: continue
            self.chat_history.append({"role":"user","content":user_input})
            try:
                resp = client.messages.create(model=PRIMARY_MODEL, max_tokens=2048,
                    system="You are a Senior HPE Journal Editor. Answer questions about the review precisely.",
                    messages=self.chat_history)
                reply = resp.content[0].text
            except Exception as e:
                try:
                    resp = client.messages.create(model=FALLBACK_MODEL, max_tokens=2048,
                        system="You are a Senior HPE Journal Editor.", messages=self.chat_history)
                    reply = resp.content[0].text
                except Exception as e2: reply = f"Error: {e2}"
            print(colored(f"\nEditor: {reply}", "cyan"))
            self.chat_history.append({"role":"assistant","content":reply})
        print(colored("Session ended.", "blue"))

def main():
    parser = argparse.ArgumentParser(description="HPE Manuscript Reviewer CLI")
    parser.add_argument("pdf", help="Path to manuscript PDF")
    parser.add_argument("--journal","-j", default="Medical Teacher", choices=JOURNALS)
    parser.add_argument("--save","-s", default="Review_Report.md")
    parser.add_argument("--criteria","-c", nargs="+", choices=list(REVIEW_CRITERIA.keys()), default=None)
    parser.add_argument("--no-chat", action="store_true")
    args = parser.parse_args()
    if not Path(args.pdf).exists(): print(colored(f"File not found: {args.pdf}","red")); sys.exit(1)
    reviewer = HPEReviewer(args.pdf, args.journal)
    report, raw, model_used = reviewer.analyze(args.criteria)
    print(colored(f"Model: {model_used}", "cyan"))
    reviewer.print_report(report, raw)
    reviewer.save(report, raw, args.save)
    if not args.no_chat: reviewer.chat_loop()

if __name__ == "__main__":
    main()
