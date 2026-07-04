"""
storage.py - Saves transcripts, recordings, and QA reports to disk.

Directory structure per call:
storage/
  scenario_01_20240629_143022/
    transcript.json       - structured transcript
    transcript.txt        - human readable transcript
    report.json           - QA analysis report
    recording.mp3         - call audio downloaded from Twilio
"""

import os
import json
import requests
from datetime import datetime

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")

STORAGE_DIR = "storage"


def _make_call_dir(scenario_id):
    """Create a directory for this call's artifacts."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    call_dir = os.path.join(STORAGE_DIR, f"{scenario_id}_{timestamp}")
    os.makedirs(call_dir, exist_ok=True)
    return call_dir


def save_transcript(scenario_id, transcript):
    """
    Save transcript as both JSON and human-readable text.

    transcript: list of {"speaker": "agent"|"patient", "text": "..."}
    Returns the call directory path.
    """
    call_dir = _make_call_dir(scenario_id)

    # JSON version
    json_path = os.path.join(call_dir, "transcript.json")
    with open(json_path, "w") as f:
        json.dump(transcript, f, indent=2)

    # Human readable version
    txt_path = os.path.join(call_dir, "transcript.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        for turn in transcript:
            speaker = turn["speaker"].upper().ljust(10)
            f.write(f"{speaker}: {turn['text']}\n")

    print(f"[storage] Transcript saved to {call_dir}")
    return call_dir


def save_report(call_dir, report):
    """Save QA analysis report as JSON."""
    report_path = os.path.join(call_dir, "report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[storage] Report saved to {report_path}")


def download_recording(call_dir, recording_url):
    """
    Download call recording from Twilio and save as mp3.
    Twilio requires basic auth to download recordings.
    """
    mp3_url = recording_url + ".mp3"
    response = requests.get(
        mp3_url,
        auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    )

    if response.status_code == 200:
        recording_path = os.path.join(call_dir, "recording.mp3")
        with open(recording_path, "wb") as f:
            f.write(response.content)
        print(f"[storage] Recording saved to {recording_path}")
    else:
        print(f"[storage] Failed to download recording: {response.status_code}")


def save_all(scenario_id, transcript, report, recording_url=None):
    """Convenience function — saves everything for a completed call."""
    call_dir = save_transcript(scenario_id, transcript)
    save_report(call_dir, report)
    if recording_url:
        download_recording(call_dir, recording_url)
    return call_dir