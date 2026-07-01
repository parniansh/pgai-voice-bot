"""
patient.py - Groq-powered patient simulator.

Flow:
1. Loaded with a scenario (persona + goal)
2. Receives agent utterances (transcribed text from transcriber.py)
3. Sends to Groq with conversation history
4. Returns patient response (text) to caller.py to be spoken
5. Signals when the call should end
"""

import os
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

SYSTEM_PROMPT_TEMPLATE = """
You are simulating a patient calling a healthcare practice's AI voice assistant.

YOUR PERSONA:
{persona}

YOUR GOAL:
{goal}

RULES:
- Stay in character at all times
- Respond naturally as a real person would on a phone call
- Keep responses concise — this is a phone call, not an essay
- Do not reveal you are an AI or a test
- React naturally to what the agent says — if they make a mistake, respond as a real patient would
- If your goal is complete or the agent has wrapped up the call, end with exactly: [END CALL]
- Do not add stage directions or narration, just speak as the patient
- Use natural speech patterns: hesitations, short sentences, conversational tone
"""


class PatientSimulator:
    def __init__(self, scenario):
        self.scenario = scenario
        self.conversation_history = []
        self.call_ended = False

        self.system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            persona=scenario["persona"],
            goal=scenario["goal"],
        )

    def respond(self, agent_utterance):
        """
        Given what the agent just said, generate the patient's response.
        Returns (response_text, should_end_call).
        """
        self.conversation_history.append({
            "role": "user",
            "content": agent_utterance
        })

        response = client.chat.completions.create(
            model="llama3-70b-8192",
            max_tokens=200,
            messages=[
                {"role": "system", "content": self.system_prompt},
                *self.conversation_history,
            ],
        )

        patient_reply = response.choices[0].message.content.strip()

        should_end = "[END CALL]" in patient_reply
        patient_reply = patient_reply.replace("[END CALL]", "").strip()

        self.conversation_history.append({
            "role": "assistant",
            "content": patient_reply
        })

        if should_end:
            self.call_ended = True
            print(f"[patient] Goal reached, ending call")

        print(f"[patient] Response: {patient_reply}")
        return patient_reply, should_end

    def get_opening_line(self):
        """Generate the patient's first line when the agent picks up."""
        opening_prompt = "The phone was just answered by the practice's AI assistant. They said a brief greeting. Start the conversation as your character would."

        response = client.chat.completions.create(
            model="llama3-70b-8192",
            max_tokens=100,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": opening_prompt},
            ],
        )

        opening_line = response.choices[0].message.content.strip()
        opening_line = opening_line.replace("[END CALL]", "").strip()

        self.conversation_history.append({"role": "user", "content": opening_prompt})
        self.conversation_history.append({"role": "assistant", "content": opening_line})

        print(f"[patient] Opening line: {opening_line}")
        return opening_line

    def reset(self):
        """Reset state for a new call."""
        self.conversation_history = []
        self.call_ended = False