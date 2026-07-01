"""
transcriber.py - Handles real-time audio transcription via Deepgram.

Flow:
1. Twilio sends audio over WebSocket to /media-stream (handled here)
2. We forward that audio to Deepgram in real time
3. Deepgram transcribes + detects end of speech (endpointing)
4. When agent finishes speaking, we fire a callback with the transcript
5. That callback triggers the patient simulator to respond
"""

import os
import json
import base64
import threading
import websocket as ws_client
from flask_sockets import Sockets
from flask import request

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")

# Deepgram WebSocket URL with config:
# - model: nova-2 (most accurate)
# - endpointing: 500ms silence = agent finished speaking
# - encoding: mulaw (Twilio's audio format)
# - sample_rate: 8000 (phone call quality)
DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2"
    "&endpointing=500"
    "&encoding=mulaw"
    "&sample_rate=8000"
    "&channels=1"
)


class Transcriber:
    def __init__(self, on_utterance):
        """
        on_utterance: callback fired when agent finishes a full utterance.
                      receives the transcribed text as argument.
        """
        self.on_utterance = on_utterance
        self.deepgram_ws = None
        self.is_running = False

    def start(self):
        """Open WebSocket connection to Deepgram."""
        self.deepgram_ws = ws_client.WebSocketApp(
            DEEPGRAM_URL,
            header={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
            on_open=self._on_deepgram_open,
            on_message=self._on_deepgram_message,
            on_error=self._on_deepgram_error,
            on_close=self._on_deepgram_close,
        )

        thread = threading.Thread(target=self.deepgram_ws.run_forever, daemon=True)
        thread.start()
        self.is_running = True
        print("[transcriber] Connected to Deepgram")

    def send_audio(self, audio_bytes):
        """Forward raw audio bytes from Twilio to Deepgram."""
        if self.deepgram_ws and self.is_running:
            self.deepgram_ws.send(audio_bytes, opcode=0x2)  # binary frame

    def stop(self):
        """Close Deepgram connection."""
        self.is_running = False
        if self.deepgram_ws:
            self.deepgram_ws.close()
        print("[transcriber] Disconnected from Deepgram")

    def _on_deepgram_open(self, ws):
        print("[transcriber] Deepgram WebSocket open")

    def _on_deepgram_message(self, ws, message):
        """
        Deepgram sends back transcription results as JSON.
        We look for is_final=True + speech_final=True which means
        the agent has finished a complete utterance.
        """
        data = json.loads(message)

        # Only process final transcripts (not interim partials)
        if data.get("type") != "Results":
            return

        is_final = data.get("is_final", False)
        speech_final = data.get("speech_final", False)  # endpointing fired

        transcript = (
            data.get("channel", {})
            .get("alternatives", [{}])[0]
            .get("transcript", "")
            .strip()
        )

        if is_final and speech_final and transcript:
            print(f"[transcriber] Agent said: {transcript}")
            self.on_utterance(transcript)  # trigger patient simulator

    def _on_deepgram_error(self, ws, error):
        print(f"[transcriber] Deepgram error: {error}")

    def _on_deepgram_close(self, ws, close_status, close_msg):
        print("[transcriber] Deepgram connection closed")


def register_media_stream_handler(app, transcriber):
    """
    Register the /media-stream WebSocket route on the Flask app.
    Twilio streams audio here in real time.
    """
    sockets = Sockets(app)

    @sockets.route("/media-stream")
    def media_stream(ws):
        """
        Twilio sends audio payloads as JSON messages over this WebSocket.
        We extract the raw audio and forward it to Deepgram.
        """
        print("[transcriber] Twilio media stream connected")
        transcriber.start()

        while not ws.closed:
            message = ws.receive()
            if message is None:
                break

            data = json.loads(message)
            event = data.get("event")

            if event == "media":
                # Audio is base64-encoded mulaw
                audio_payload = data["media"]["payload"]
                audio_bytes = base64.b64decode(audio_payload)
                transcriber.send_audio(audio_bytes)

            elif event == "stop":
                print("[transcriber] Twilio stream stopped")
                break

        transcriber.stop()