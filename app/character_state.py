"""Thread-safe character animation state shared between the controller and
the character page.

The character page polls /api/state. When the controller is speaking, the
page also receives a mouth amplitude (0.0-1.0) derived from the real RMS
envelope of the TTS audio being played, so the mouth moves with the audio
instead of a fixed loop.
"""

import threading
import time

VALID_STATES = ("idle", "listening", "working", "speaking")


class CharacterState:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = "idle"
        self._envelope = []
        self._envelope_start = 0.0
        self._envelope_step = 0.05  # seconds per envelope sample

    def set_state(self, state):
        if state not in VALID_STATES:
            raise ValueError(f"unknown character state: {state!r}")
        with self._lock:
            self._state = state
            if state != "speaking":
                self._envelope = []

    def get_state(self):
        with self._lock:
            return self._state

    def set_envelope(self, envelope, step=0.05):
        """Store a TTS amplitude envelope and stamp its start time."""
        with self._lock:
            self._envelope = list(envelope)
            self._envelope_step = step
            self._envelope_start = time.time()

    def amplitude(self):
        """Current mouth amplitude for the speaking state, else 0.0."""
        with self._lock:
            if self._state != "speaking" or not self._envelope:
                return 0.0
            idx = int((time.time() - self._envelope_start) / self._envelope_step)
            if idx < 0 or idx >= len(self._envelope):
                return 0.0
            return float(self._envelope[idx])

    def snapshot(self):
        return {"state": self.get_state(), "amplitude": self.amplitude()}


# Process-wide singleton used by main.py, speak.py and the API.
STATE = CharacterState()
