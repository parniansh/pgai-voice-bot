"""
analyzer.py - Groq-powered QA analyzer.

Flow:
1. Receives full call transcript after call ends
2. Loads scenario success_criteria + global_criteria
3. Sends both to Groq for analysis
4. Returns structured bug report
"""

import os
import json
import time
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

ANALYZER_PROMPT = """
You are a QA analyst evaluating an AI healthcare voice assistant.

You will be given:
1. A call transcript between a simulated patient and the AI agent
2. Global criteria that should be met on every call
3. Scenario-specific success criteria for this particular call

Your job is to identify bugs, failures, and quality issues in the AGENT's responses only.
Do not critique the patient simulator.

Respond in JSON only. No preamble. No markdown. Exact format:

{{
  "scenario_id": "{scenario_id}",
  "scenario_name": "{scenario_name}",
  "overall_pass": true or false,
  "bugs": [
    {{
      "severity": "high | medium | low",
      "criteria_violated": "which criterion was violated",
      "timestamp_approx": "approximate point in conversation",
      "what_happened": "what the agent did",
      "what_should_have_happened": "what the agent should have done"
    }}
  ],
  "global_criteria_results": [
    {{
      "criterion": "criterion text",
      "passed": true or false,
      "note": "brief explanation if failed"
    }}
  ],
  "scenario_criteria_results": [
    {{
      "criterion": "criterion text",
      "passed": true or false,
      "note": "brief explanation if failed"
    }}
  ],
  "summary": "2-3 sentence overall assessment"
}}
"""


class Analyzer:
    def __init__(self, global_criteria):
        self.global_criteria = global_criteria

    def analyze(self, transcript, scenario):
        """
        Analyze a call transcript against global and scenario-specific criteria.
        Returns parsed JSON report dict.
        """
        transcript_text = self._format_transcript(transcript)

        prompt = f"""
{ANALYZER_PROMPT.format(
    scenario_id=scenario['id'],
    scenario_name=scenario['name']
)}

GLOBAL CRITERIA (must pass on every call):
{json.dumps(self.global_criteria, indent=2)}

SCENARIO-SPECIFIC CRITERIA:
{json.dumps(scenario['success_criteria'], indent=2)}

TRANSCRIPT:
{transcript_text}
"""

        t0 = time.perf_counter()
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        print(f"[analyzer] Groq responded in {time.perf_counter() - t0:.2f}s")

        raw = response.choices[0].message.content.strip()

        try:
            report = json.loads(raw)
        except json.JSONDecodeError:
            report = {
                "scenario_id": scenario["id"],
                "scenario_name": scenario["name"],
                "overall_pass": False,
                "bugs": [],
                "summary": "Analysis failed to parse. Raw output: " + raw,
            }

        self._print_report(report)
        return report

    def _format_transcript(self, transcript):
        lines = []
        for turn in transcript:
            speaker = turn["speaker"].upper()
            text = turn["text"]
            lines.append(f"{speaker}: {text}")
        return "\n".join(lines)

    def _print_report(self, report):
        print(f"\n[analyzer] ---- QA Report: {report['scenario_name']} ----")
        print(f"[analyzer] Overall: {'PASS' if report['overall_pass'] else 'FAIL'}")
        bugs = report.get("bugs", [])
        if bugs:
            print(f"[analyzer] Bugs found: {len(bugs)}")
            for bug in bugs:
                print(f"  [{bug['severity'].upper()}] {bug['what_happened']}")
        else:
            print("[analyzer] No bugs found")
        print(f"[analyzer] Summary: {report.get('summary', '')}")
        print("[analyzer] " + "-" * 40)