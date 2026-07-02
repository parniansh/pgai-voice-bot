"""
transcriber.py - Handles real-time audio transcription via Deepgram.
"""

import os
import json
import base64
import threading
import websocket as ws_client

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")

DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2"
    "&endpointing=500"
    "&encoding=mulaw"
    "&sample_rate=8000"
    "&channels=1"
)

_current_transcriber = None


def set_active_transcriber(transcriber):
    global _current_transcriber
    _current_transcriber = transcriber


class Transcriber:
    def __init__(self, on_utterance):
        self.on_utterance = on_utterance
        self.deepgram_ws = None
        self.is_running = False
        self.muted = False

    def start(self):
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
        if self.deepgram_ws and self.is_running:
            try:
                self.deepgram_ws.send(audio_bytes, opcode=0x2)
            except Exception as e:
                print(f"[transcriber] Error sending audio: {e}")

    def stop(self):
        self.is_running = False
        if self.deepgram_ws:
            self.deepgram_ws.close()
        print("[transcriber] Disconnected from Deepgram")

    def _on_deepgram_open(self, ws):
        print("[transcriber] Deepgram WebSocket open")

    def _on_deepgram_message(self, ws, message):
        data = json.loads(message)
        if data.get("type") != "Results":
            return

        is_final = data.get("is_final", False)
        speech_final = data.get("speech_final", False)
        transcript = (
            data.get("channel", {})
            .get("alternatives", [{}])[0]
            .get("transcript", "")
            .strip()
        )

        if is_final and speech_final and transcript:
            print(f"[transcriber] Agent said: {transcript}")
            self.on_utterance(transcript)

    def _on_deepgram_error(self, ws, error):
        print(f"[transcriber] Deepgram error: {error}")

    def _on_deepgram_close(self, ws, close_status, close_msg):
        print("[transcriber] Deepgram connection closed")


def register_media_stream_handler(app):
    """Register /media-stream WebSocket route using flask-sock. Call once before server starts."""
    from flask_sock import Sock
    sock = Sock(app)

    @sock.route("/media-stream")
    def media_stream(ws):
        print("[transcriber] Twilio media stream connected")
        transcriber = _current_transcriber
        if transcriber is None:
            return

        transcriber.start()
        owned_dg_ws = transcriber.deepgram_ws  # snapshot before loop
        try:
            while ws.connected:
                message = ws.receive()
                if message is None:
                    break

                data = json.loads(message)
                event = data.get("event")

                if event == "media":
                    audio_bytes = base64.b64decode(data["media"]["payload"])
                    transcriber.send_audio(audio_bytes)
                elif event == "stop":
                    print("[transcriber] Twilio stream stopped")
                    break
        except Exception:
            pass
        finally:
            # Only close the Deepgram connection this handler owns.
            # transcriber.stop() would close self.deepgram_ws, which may
            # already point to a newer connection opened by the next turn.
            transcriber.is_running = False
            if owned_dg_ws:
                owned_dg_ws.close()
