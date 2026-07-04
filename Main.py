from gevent import monkey
monkey.patch_all()

"""
main.py - Orchestrator for the voice bot testing framework.

Usage:
  python main.py --scenario scenario_01   # run one scenario
  python main.py --all                     # run all scenarios
  python main.py                           # does nothing
"""

import os
import json
import time
import threading
import argparse
from dotenv import load_dotenv

load_dotenv()

import Caller
import Transcriber as transcriber_module
import Storage
from Patient import PatientSimulator
from Analyzer import Analyzer

SCENARIOS_PATH = "Scenarios.json"

# Mutable callback reference — updated per scenario without re-registering the route
current_on_utterance = [None]


def load_scenarios():
    with open(SCENARIOS_PATH) as f:
        data = json.load(f)
    return data["global_criteria"], data["scenarios"]


def run_scenario(scenario, analyzer):
    """Run a single test scenario end to end."""
    print(f"\n{'='*50}")
    print(f"[main] Running: {scenario['id']} - {scenario['name']}")
    print(f"{'='*50}")

    transcript = []
    recording_url = [None]
    call_sid = [None]
    call_done = threading.Event()
    patient = PatientSimulator(scenario)

    def on_utterance(agent_text):
        if call_done.is_set():
            return

        time.sleep(0.5)  # wait for agent TTS to fully finish before responding

        transcript.append({"speaker": "agent", "text": agent_text})

        patient_reply = patient.respond(agent_text)
        transcript.append({"speaker": "patient", "text": patient_reply})

        Caller.speak(patient_reply)

    def on_call_ended():
        print(f"[main] Call ended for {scenario['id']}")
        call_done.set()

    def on_recording_ready(url):
        recording_url[0] = url

    # Update callback reference for this scenario
    current_on_utterance[0] = on_utterance
    Caller.on_call_ended_callback = on_call_ended
    Caller.on_recording_ready_callback = on_recording_ready

    call_sid[0] = Caller.make_call()
    print(f"[main] Call SID: {call_sid[0]}")
    print(f"[main] Waiting for agent to speak...")

    finished = call_done.wait(timeout=300)
    if not finished:
        print(f"[main] Timed out — ending call")
        Caller.end_call(call_sid[0])

    time.sleep(5)

    print(f"[main] Analyzing transcript...")
    report = analyzer.analyze(transcript, scenario)

    call_dir = Storage.save_all(
        scenario_id=scenario["id"],
        transcript=transcript,
        report=report,
        recording_url=recording_url[0],
    )

    print(f"[main] Artifacts saved to {call_dir}")
    return report


def print_summary(results):
    print(f"\n{'='*50}")
    print("[main] FINAL SUMMARY")
    print(f"{'='*50}")
    total = len(results)
    passed = sum(1 for r in results if r.get("overall_pass"))
    print(f"Total: {total} | Passed: {passed} | Failed: {total - passed}")
    print()
    for r in results:
        status = "PASS" if r.get("overall_pass") else "FAIL"
        bugs = len(r.get("bugs", []))
        print(f"  {r['scenario_id']} | {status} | {bugs} bug(s) | {r['scenario_name']}")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description="Voice bot testing framework")
    parser.add_argument("--scenario", type=str, help="Run a specific scenario by ID")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    args = parser.parse_args()

    if not args.scenario and not args.all:
        return

    # Register WebSocket handler once at startup — routes through current_on_utterance
    transcriber_module.register_conversation_relay_handler(
        lambda text: current_on_utterance[0](text) if current_on_utterance[0] else None
    )

    Caller.start()

    # Wait until server is actually ready
    import requests as req
    for _ in range(20):
        try:
            req.get('http://localhost:5000/health', timeout=1)
            print('[main] Server ready')
            break
        except Exception:
            time.sleep(0.5)

    global_criteria, scenarios = load_scenarios()
    analyzer = Analyzer(global_criteria)

    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
        if not scenarios:
            print(f"[main] Scenario {args.scenario} not found")
            return

    results = []
    for scenario in scenarios:
        report = run_scenario(scenario, analyzer)
        results.append(report)
        time.sleep(10)

    print_summary(results)


if __name__ == "__main__":
    main()