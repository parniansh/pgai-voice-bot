"""
main.py - Orchestrator for the voice bot testing framework.

Flow:
1. Load scenarios from scenarios.json
2. Start Flask webhook server
3. For each scenario:
   a. Initialize patient simulator with scenario
   b. Make outbound call via Twilio
   c. Handle turns: transcribe agent → simulate patient → speak response
   d. When call ends: analyze transcript → save everything
4. Print final summary of all results
"""

import os
import json
import time
import argparse
from dotenv import load_dotenv

load_dotenv()

import caller
import transcriber as transcriber_module
import storage
from patient import PatientSimulator
from analyzer import Analyzer

SCENARIOS_PATH = "scenarios/scenarios.json"


def load_scenarios():
    with open(SCENARIOS_PATH) as f:
        data = json.load(f)
    return data["global_criteria"], data["scenarios"]


def run_scenario(scenario, analyzer):
    """Run a single test scenario end to end."""
    print(f"\n{'='*50}")
    print(f"[main] Running scenario: {scenario['id']} - {scenario['name']}")
    print(f"{'='*50}")

    # State for this call
    transcript = []
    call_sid = None
    recording_url = None
    call_active = True
    patient = PatientSimulator(scenario)

    def on_utterance(agent_text):
        """Called by transcriber when agent finishes speaking."""
        nonlocal call_active

        if not call_active:
            return

        # Save agent turn to transcript
        transcript.append({"speaker": "agent", "text": agent_text})

        # Generate patient response
        patient_reply, should_end = patient.respond(agent_text)

        # Save patient turn to transcript
        transcript.append({"speaker": "patient", "text": patient_reply})

        # Speak the patient response into the call
        caller.speak(call_sid, patient_reply)

        if should_end:
            call_active = False
            time.sleep(2)  # give Twilio time to speak final line
            end_call(call_sid)

    def on_call_ended():
        """Called by caller when Twilio signals call is complete."""
        nonlocal call_active
        call_active = False
        print(f"[main] Call ended for {scenario['id']}")

    # Register callbacks
    caller.on_transcription_callback = on_utterance
    caller.on_call_ended_callback = on_call_ended

    # Start transcriber for this call
    transcr = transcriber_module.Transcriber(on_utterance=on_utterance)
    transcriber_module.register_media_stream_handler(caller.app, transcr)

    # Make the call
    call_sid = caller.make_call()
    print(f"[main] Call SID: {call_sid}")

    # Wait for call to connect then send opening line
    time.sleep(5)
    opening_line = patient.get_opening_line()
    transcript.append({"speaker": "patient", "text": opening_line})
    caller.speak(call_sid, opening_line)

    # Wait for call to finish (max 5 minutes)
    timeout = 300
    elapsed = 0
    while call_active and elapsed < timeout:
        time.sleep(1)
        elapsed += 1

    if elapsed >= timeout:
        print(f"[main] Call timed out for {scenario['id']}")
        end_call(call_sid)

    # Small delay to ensure recording is available
    time.sleep(5)

    # Analyze the transcript
    print(f"[main] Analyzing transcript for {scenario['id']}...")
    report = analyzer.analyze(transcript, scenario)

    # Save everything
    call_dir = storage.save_all(
        scenario_id=scenario["id"],
        transcript=transcript,
        report=report,
        recording_url=recording_url,
    )

    print(f"[main] All artifacts saved to {call_dir}")
    return report


def end_call(call_sid):
    """Hang up the call via Twilio."""
    try:
        from twilio.rest import Client
        client = Client(os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN"))
        client.calls(call_sid).update(status="completed")
        print(f"[main] Call {call_sid} ended")
    except Exception as e:
        print(f"[main] Error ending call: {e}")


def print_summary(results):
    """Print a final summary table of all scenario results."""
    print(f"\n{'='*50}")
    print("[main] FINAL SUMMARY")
    print(f"{'='*50}")
    total = len(results)
    passed = sum(1 for r in results if r.get("overall_pass"))
    failed = total - passed
    print(f"Total scenarios: {total} | Passed: {passed} | Failed: {failed}")
    print()
    for result in results:
        status = "PASS" if result.get("overall_pass") else "FAIL"
        bugs = len(result.get("bugs", []))
        print(f"  {result['scenario_id']} | {status} | {bugs} bug(s) | {result['scenario_name']}")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description="Voice bot testing framework")
    parser.add_argument("--scenario", type=str, help="Run a specific scenario by ID (e.g. scenario_01)")
    parser.add_argument("--all", action="store_true", help="Run all scenarios sequentially")
    args = parser.parse_args()

    # Start Flask webhook server
    caller.start()
    time.sleep(1)  # give server time to start

    # Load scenarios
    global_criteria, scenarios = load_scenarios()
    analyzer = Analyzer(global_criteria)

    # Filter scenarios if specific one requested
    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
        if not scenarios:
            print(f"[main] Scenario {args.scenario} not found")
            return

    results = []
    for scenario in scenarios:
        report = run_scenario(scenario, analyzer)
        results.append(report)
        time.sleep(10)  # pause between calls to avoid rate limits

    print_summary(results)


if __name__ == "__main__":
    main()