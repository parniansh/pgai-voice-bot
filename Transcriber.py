"""
transcriber.py - Handles the Conversation Relay WebSocket connection.

Buffers agent utterances and only fires on_utterance after a pause,
so the patient waits for the agent to finish their full thought.
"""

import json
import threading
import Caller

BUFFER_DELAY = 2  # seconds to wait after last agent sentence before responding


def register_conversation_relay_handler(on_utterance):
    """Register /conversation-relay WebSocket route on Caller.sock."""

    @Caller.sock.route("/conversation-relay")
    def conversation_relay(ws):
        print("[transcriber] Conversation Relay WebSocket connected")
        Caller.active_ws = ws

        buffer = []
        flush_timer = [None]

        def flush():
            if buffer:
                full_text = " ".join(buffer)
                buffer.clear()
                print(f"[transcriber] Agent said: {full_text}")
                on_utterance(full_text)

        while True:
            try:
                message = ws.receive()
            except Exception as e:
                print(f"[transcriber] WebSocket error: {e}")
                break

            if message is None:
                break

            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "setup":
                print(f"[transcriber] Call setup: {data.get('callSid')}")

            elif msg_type == "prompt":
                agent_text = data.get("voicePrompt", "").strip()
                if agent_text:
                    buffer.append(agent_text)

                    # Cancel existing timer and start a new one
                    if flush_timer[0]:
                        flush_timer[0].cancel()
                    flush_timer[0] = threading.Timer(BUFFER_DELAY, flush)
                    flush_timer[0].start()

            elif msg_type == "interrupt":
                print(f"[transcriber] Agent interrupted TTS")
                # Cancel pending flush on interrupt
                if flush_timer[0]:
                    flush_timer[0].cancel()
                buffer.clear()

            elif msg_type == "error":
                print(f"[transcriber] Error: {data.get('description')}")

        # Cancel any pending timer on disconnect
        if flush_timer[0]:
            flush_timer[0].cancel()

        Caller.active_ws = None
        print("[transcriber] Conversation Relay WebSocket disconnected")