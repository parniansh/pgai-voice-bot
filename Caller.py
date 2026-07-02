"""
caller.py - Handles outbound calls via Twilio and manages the media stream.
"""

import os
import time
import threading
from flask import Flask, request, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

app = Flask(__name__)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
NGROK_URL = os.environ.get("NGROK_URL")

TARGET_NUMBER = "+18054398008"

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

on_call_ended_callback = None
on_recording_ready_callback = None
current_call_sid = None


def make_call():
    global current_call_sid
    call = twilio_client.calls.create(
        to=TARGET_NUMBER,
        from_=TWILIO_PHONE_NUMBER,
        url=f"{NGROK_URL}/call-connected",
        status_callback=f"{NGROK_URL}/call-ended",
        status_callback_event=["completed"],
        record=True,
        recording_status_callback=f"{NGROK_URL}/recording-ready",
    )
    current_call_sid = call.sid
    print(f"[caller] Call initiated: {call.sid}")
    return call.sid


@app.route("/call-connected", methods=["POST"])
def call_connected():
    """Twilio hits this when call connects — open a media stream."""
    response = VoiceResponse()
    connect = Connect()
    # Use wss:// for the media stream WebSocket
    stream = Stream(url=f"{NGROK_URL.replace('https://', 'wss://')}/media-stream")
    connect.append(stream)
    response.append(connect)
    print("[caller] Call connected, opening media stream")
    return Response(str(response), mimetype="text/xml")


@app.route("/call-ended", methods=["POST"])
def call_ended():
    print("[caller] Call ended")
    if on_call_ended_callback:
        on_call_ended_callback()
    return Response("", status=200)


@app.route("/recording-ready", methods=["POST"])
def recording_ready():
    recording_url = request.form.get("RecordingUrl")
    print(f"[caller] Recording ready: {recording_url}")
    if on_recording_ready_callback:
        on_recording_ready_callback(recording_url)
    return Response("", status=200)


def speak(call_sid, text):
    """Inject patient speech into the live call via Twilio TTS."""
    try:
        t0 = time.perf_counter()
        twilio_client.calls(call_sid).update(
            twiml=f"<Response><Say voice='Polly.Joanna'>{text}</Say><Redirect>{NGROK_URL}/call-connected</Redirect></Response>"
        )
        print(f"[caller] Twilio TTS delivered in {time.perf_counter() - t0:.2f}s")
        print(f"[caller] Speaking: {text}")
    except Exception as e:
        print(f"[caller] Error speaking: {e}")


def end_call(call_sid):
    try:
        twilio_client.calls(call_sid).update(status="completed")
        print(f"[caller] Ended call {call_sid}")
    except Exception as e:
        print(f"[caller] Error ending call: {e}")


def start():
    """Start Flask server with WebSocket support via flask-sock."""
    thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=5000, debug=False),
        daemon=True,
    )
    thread.start()
    print("[caller] Webhook server running on port 5000")