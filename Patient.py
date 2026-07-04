"""
patient.py - Groq-powered patient simulator.
"""

import os
import time
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

SYSTEM_PROMPT_TEMPLATE = """You are a patient calling a healthcare practice's AI voice assistant. You are having a real phone conversation.

YOUR PERSONA:
{persona}

YOUR GOAL FOR THIS CALL:
{goal}

HOW TO BEHAVE:
- Speak naturally as this specific person would on a phone call
- Actively steer the conversation toward your goal — if the agent goes off track, bring it back
- Give information when asked, but do not volunteer everything at once
- React realistically to what the agent says — confusion, frustration, relief, as appropriate
- Keep each response short — 1-2 sentences, as in a real phone call
- If the agent says something wrong or unhelpful, respond as a real patient would (push back, ask for clarification, express frustration)
- Do NOT output stage directions, brackets, meta-commentary, or anything other than what you would say out loud
- Never reveal you are an AI, a bot, or part of a test — you are a real patient"""


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
        self.conversation_history.append({
            "role": "user",
            "content": agent_utterance
        })

        t0 = time.time()
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            max_tokens=150,
            messages=[
                {"role": "system", "content": self.system_prompt},
                *self.conversation_history,
            ],
        )

        patient_reply = response.choices[0].message.content.strip()
        print(f"[patient] Groq response time: {time.time() - t0:.2f}s")

        patient_reply = patient_reply.rstrip(".").strip()

        if not patient_reply:
            patient_reply = "Sorry, could you repeat that?"

        self.conversation_history.append({
            "role": "assistant",
            "content": patient_reply
        })

        print(f"[patient] Response: {patient_reply}")
        return patient_reply

    def reset(self):
        self.conversation_history = []
        self.call_ended = False