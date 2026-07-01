"""
caller.py - Handles outbound calls via Twilio and manages the media stream.

Flow:
1. Make outbound call via Twilio REST API
2. Twilio hits our Flask webhook when call connects
3. We open a media stream to receive/send audio
4. Incoming audio is passed to transcriber
5. Patient responses (text) are spoken back via Twilio TTS
"""

import os
import json
import threading
from flask import Flask, request, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream, Say
import websocket

app = Flask(__name__)

# Twilio credentials from environment
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
NGROK_URL = os.environ.get("NGROK_URL")  # e.g. https://abc123.ngrok.io

TARGET_NUMBER = "+18054398008"  # Pretty Good AI test number

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Will be set by main.py before making a call
current_scenario = None
on_transcription_callback = None  # called when agent speech is transcribed
on_call_ended_callback = None     # called when call ends


def make_call():
    """Initiate an outbound call to the test number."""
    call = twilio_client.calls.create(
        to=TARGET_NUMBER,
        from_=TWILIO_PHONE_NUMBER,
        url=f"{NGROK_URL}/call-connected",  # Twilio hits this when call connects
        status_callback=f"{NGROK_URL}/call-ended",
        status_callback_event=["completed"],
        record=True,  # record the full call
        recording_status_callback=f"{NGROK_URL}/recording-ready",
    )
    print(f"[caller] Call initiated: {call.sid}")
    return call.sid


@app.route("/call-connected", methods=["POST"])
def call_connected():
    """
    Twilio hits this when the call connects.
    We respond with TwiML to open a media stream.
    """
    response = VoiceResponse()

    # Open a WebSocket media stream — this gives us real-time audio
    connect = Connect()
    stream = Stream(url=f"wss://{NGROK_URL.replace('https://', '')}/media-stream")
    connect.append(stream)
    response.append(connect)

    return Response(str(response), mimetype="text/xml")


@app.route("/call-ended", methods=["POST"])
def call_ended():
    """Twilio hits this when the call ends."""
    print("[caller] Call ended")
    if on_call_ended_callback:
        on_call_ended_callback()
    return Response("", status=200)


@app.route("/recording-ready", methods=["POST"])
def recording_ready():
    """Twilio hits this when the recording is available."""
    recording_url = request.form.get("RecordingUrl")
    recording_sid = request.form.get("RecordingSid")
    print(f"[caller] Recording ready: {recording_url}")
    # Storage module will download this
    return Response("", status=200)


def speak(call_sid, text):
    """
    Inject patient speech into the live call.
    Uses Twilio's TTS to speak the given text.
    Note: ElevenLabs can replace this later for better voice quality.
    """
    twilio_client.calls(call_sid).update(
        twiml=f"<Response><Say voice='Polly.Joanna'>{text}</Say></Response>"
    )
    print(f"[caller] Speaking: {text}")


def run_server():
    """Run the Flask webhook server in a background thread."""
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


def start():
    """Start the Flask server in background and return."""
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    print("[caller] Webhook server running on port 5000")