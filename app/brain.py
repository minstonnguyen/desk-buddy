"""Local LLM brain via the Ollama HTTP API.

No API keys, no cloud: Ollama serves open-weights models on localhost.
The default model is qwen2.5:3b (small enough for a laptop CPU/GPU mix,
coherent enough for short meeting replies). Change it in config.json and
run `ollama pull <model>` yourself.
"""

import logging

import httpx

log = logging.getLogger("desk-buddy.brain")

SYSTEM_PROMPT = (
    "You are Desk Buddy, a helpful personal assistant sitting in a work "
    "meeting. Answer briefly, in 1-3 sentences, unless the person clearly "
    "asks for more detail. Be direct and plain-spoken. Never claim to be "
    "human. If you do not know something, say so."
)


class Brain:
    def __init__(self, config):
        self.base_url = config["ollama"]["base_url"].rstrip("/")
        self.model = config["ollama"]["model"]
        self.timeout = config["ollama"]["timeout_seconds"]

    def reply(self, utterance, recent_transcript=""):
        """Generate a short reply to `utterance` given recent transcript context."""
        prompt = SYSTEM_PROMPT + "\n\n"
        if recent_transcript:
            prompt += "Recent meeting transcript:\n" + recent_transcript + "\n\n"
        prompt += "Someone just said to you: " + utterance + "\nReply:"
        try:
            resp = httpx.post(
                self.base_url + "/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
            if not text:
                return "I heard you, but I don't have a good answer for that."
            return text
        except httpx.ConnectError:
            log.error("cannot reach Ollama at %s — is it running?", self.base_url)
            return (
                "I can't reach my local brain right now. "
                "Make sure Ollama is running and the model is pulled."
            )
        except Exception as exc:  # noqa: BLE001 - surface any Ollama failure as speech
            log.exception("Ollama request failed")
            return f"Something went wrong asking my local model: {exc}"
