"""Local text-to-speech with Piper, played into the VB-Cable device.

Pipeline: text -> piper.exe -> WAV file -> RMS amplitude envelope (stored
in the shared character state so the character page's mouth moves with the
real audio) -> playback through the VB-Cable input device, which Teams is
listening to as its microphone.

If VB-Cable is not installed, playback falls back to the default output
device with a loud warning in the log, so the failure is obvious instead
of silent.
"""

import logging
import math
import os
import struct
import subprocess
import tempfile
import wave

import sounddevice as sd

from .audio import find_output_device
from .character_state import STATE

log = logging.getLogger("desk-buddy.speak")

ENVELOPE_STEP = 0.05  # seconds per amplitude sample


def _rms_envelope(wav_path, step=ENVELOPE_STEP):
    """Compute a normalized 0..1 RMS amplitude envelope from a WAV file."""
    with wave.open(wav_path, "rb") as wav:
        n_frames = wav.getnframes()
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        raw = wav.readframes(n_frames)
    if width == 2:
        fmt = "<%dh" % (len(raw) // 2)
        samples = struct.unpack(fmt, raw)
    elif width == 4:
        fmt = "<%di" % (len(raw) // 4)
        samples = struct.unpack(fmt, raw)
        samples = [s / 32768.0 for s in samples]
        peak = max((abs(s) for s in samples), default=0.0) or 1.0
        samples = [s / peak for s in samples]
    else:  # 8-bit unsigned
        samples = [(b - 128) / 128.0 for b in raw]
    if channels > 1:
        samples = samples[::channels]
    window = max(1, int(rate * step))
    envelope = []
    peak = 0.0
    windows = []
    for start in range(0, len(samples), window):
        chunk = samples[start : start + window]
        if not chunk:
            continue
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
        windows.append(rms)
        peak = max(peak, rms)
    peak = peak or 1.0
    for rms in windows:
        envelope.append(round(min(1.0, rms / peak), 3))
    return envelope


def _play_wav(wav_path, device_index):
    """Play a WAV file to a specific output device, blocking until done."""
    with wave.open(wav_path, "rb") as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())
    if width == 2:
        import numpy as np

        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        import numpy as np

        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
    if channels > 1:
        data = data.reshape(-1, channels)
    sd.play(data, samplerate=rate, device=device_index)
    sd.wait()


def speak_text(text, config):
    """Synthesize `text` with Piper and play it into the Teams mic device.

    Returns the path of the generated WAV (in the temp dir) for debugging.
    Raises RuntimeError with a plain message if Piper is missing.
    """
    piper_exe = config["piper"]["exe"]
    voice = config["piper"]["voice"]
    if not os.path.exists(piper_exe):
        raise RuntimeError(
            f"Piper not found at {piper_exe}. Run scripts/download_models.ps1 first."
        )
    if not os.path.exists(voice):
        raise RuntimeError(
            f"Piper voice model not found at {voice}. "
            "Run scripts/download_models.ps1 first."
        )
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        result = subprocess.run(
            [piper_exe, "--model", voice, "--output_file", tmp.name],
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Piper failed: {result.stderr.decode(errors='replace')}")
        envelope = _rms_envelope(tmp.name)
        STATE.set_envelope(envelope, step=ENVELOPE_STEP)
        device = find_output_device(config)
        log.info("playing %d chars of speech to output device %r", len(text), device)
        _play_wav(tmp.name, device)
        return tmp.name
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
