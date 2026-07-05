# PGAI Voice Bot Testing Framework

Automated voice bot that calls Pretty Good AI's test line (+1-805-439-8008), simulates realistic patient phone calls, transcribes the conversation, and generates a QA bug report against the agent's responses.

## Architecture

The bot places an outbound call via Twilio and connects it to **Conversation Relay**, which keeps a single persistent WebSocket open for the full duration of the call and handles STT/TTS internally. An earlier version used the Twilio REST API's `speak()` pattern with Deepgram for transcription, but that approach tore down and rebuilt the media stream on every turn, which capped conversations at one exchange. Conversation Relay removes that limitation: Twilio streams the agent's transcribed speech to us over the WebSocket as `prompt` messages, we generate a patient reply, and send it back as a text token that Twilio converts to speech.

The system is split into six modules: `caller.py` (Twilio outbound call + Conversation Relay webhook server, Flask + flask-sock + gevent), `transcriber.py` (WebSocket message handling and utterance buffering, so the patient doesn't respond mid-sentence), `patient.py` (Groq-backed patient simulator that holds conversation history and follows a scenario-specific system prompt), `analyzer.py` (post-call QA pass that grades the transcript against global and scenario-specific criteria and returns structured JSON), `storage.py` (writes transcripts, recordings, and reports to timestamped per-scenario folders), and `main.py` (orchestrates a scenario end-to-end and signals call completion across threads via `threading.Event`). Both the patient simulator and the QA analyzer run on Groq's `openai/gpt-oss-120b`. Scenarios live in `scenarios/scenarios.json` as a single file with `global_criteria` (rules that apply to every call) and per-scenario `success_criteria` — the target agent is a triage bot that collects patient identity and redirects the call rather than completing scheduling or refills, so scenarios and grading are written around that behavior.

## Setup

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```
   Required variables:
   | Variable | Description |
   |---|---|
   | `TWILIO_ACCOUNT_SID` | Twilio account SID |
   | `TWILIO_AUTH_TOKEN` | Twilio auth token |
   | `TWILIO_PHONE_NUMBER` | The Twilio number the bot calls *from* |
   | `NGROK_URL` | Public HTTPS URL for the Conversation Relay webhook (see step 3) |
   | `GROQ_API_KEY` | Groq API key (patient simulator + QA analyzer) |
3. Expose your local server so Twilio can reach it, and copy the `https` URL into `NGROK_URL` in `.env`:
   ```bash
   ngrok http 5000
   ```
4. In the Twilio console, complete the Conversation Relay onboarding (accept the AI/ML addendum) — required before Conversation Relay calls will connect.

## Running

```bash
python main.py --scenario scenario_01   # run a single scenario
python main.py --all                    # run all scenarios in scenarios/scenarios.json
```

Each run places a real call to +1-805-439-8008, drives the conversation using the scenario's patient persona, and on completion writes the recording, transcript, and QA report to a timestamped folder under `storage/`.

## Output

For each call, `storage/<timestamp>_<scenario_id>/` contains:
- the call recording (audio)
- `transcript.txt` — full turn-by-turn conversation
- `report.json` — QA analyzer output: pass/fail against criteria, bugs found with severity, and a summary

See `BUGS.md` for the consolidated bug report across all test calls.

## Notes

- There's a 10-second pause between calls in `--all` mode to avoid rate limits, and a timeout safety net per call in case a call gets stuck.
- Only call the assigned test number (+1-805-439-8008) — this bot is not meant to dial anywhere else.
