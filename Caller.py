"""
caller.py - Handles outbound calls via Twilio using Conversation Relay.
"""

import os
import json
import threading
from flask import Flask, request, Response
from flask_sock import Sock
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect

app = Flask(__name__)
sock = Sock(app)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
NGROK_URL = os.environ.get("NGROK_URL")

TARGET_NUMBER = "+18054398008"

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

on_call_ended_callback = None
on_recording_ready_callback = None
active_ws = None



@app.route('/health', methods=['GET'])
def health():
    return Response('ok', status=200)

def make_call():
    call = twilio_client.calls.create(
        to=TARGET_NUMBER,
        from_=TWILIO_PHONE_NUMBER,
        url=f"{NGROK_URL}/call-connected",
        status_callback=f"{NGROK_URL}/call-ended",
        status_callback_event=["completed"],
        record=True,
        recording_status_callback=f"{NGROK_URL}/recording-ready",
    )
    print(f"[caller] Call initiated: {call.sid}")
    return call.sid


@app.route("/call-connected", methods=["POST"])
def call_connected():
    response = VoiceResponse()
    connect = Connect()
    connect.conversation_relay(
        url=f"{NGROK_URL.replace('https://', 'wss://')}/conversation-relay",
        transcription_provider="Deepgram",
        tts_provider="Amazon",
        voice="Matthew-Neural",
        language="en-US",
    )
    response.append(connect)
    print("[caller] Call connected, starting Conversation Relay")
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


def speak(text):
    global active_ws
    if active_ws:
        message = json.dumps({"type": "text", "token": text, "last": True})
        active_ws.send(message)
        print(f"[caller] Speaking: {text}")
    else:
        print("[caller] No active WebSocket to speak on")


def end_call_via_ws():
    global active_ws
    if active_ws:
        active_ws.send(json.dumps({"type": "end"}))
        print("[caller] Sent end session message")


def end_call(call_sid):
    try:
        twilio_client.calls(call_sid).update(status="completed")
        print(f"[caller] Ended call {call_sid}")
    except Exception as e:
        print(f"[caller] Error ending call: {e}")


def start():
    """
    Run Flask with gevent as the async backend.
    flask-sock handles WebSocket upgrades, gevent handles persistent connections.
    HTTP and WebSocket share the same port — ngrok forwards both transparently.
    """
    from gevent import pywsgi

    server = pywsgi.WSGIServer(("0.0.0.0", 5000), app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print("[caller] Server running on port 5000 (HTTP + WebSocket)")