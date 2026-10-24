"""Live meeting transcription with faster-whisper on CPU.

Audio is captured from a loopback-style input device (a device named
"loopback", "Stereo Mix", or "What U Hear" — see app/audio.py), sliced
into chunks of `whisper.chunk_seconds`, and transcribed with faster-whisper.
Each finished chunk is appended to transcripts/YYYY-MM-DD.md with a
timestamp and delivered to an optional callback (used by the wake-word
monitor in main.py).

This module is also runnable standalone for debugging:
    python -m app.transcribe --list-devices   # print audio devices
    python -m app.transcribe --test 10        # transcribe 10 seconds
"""

import argparse
import datetime
import logging
import os
import queue
import threading

import numpy as np
import sounddevice as sd

from .audio import find_loopback_device, list_devices

log = logging.getLogger("desk-buddy.transcribe")


class Transcriber:
    def __init__(self, config, on_segment=None):
        self.config = config
        self.on_segment = on_segment
        self._running = False
        self._thread = None
        self._model = None
        self.segments = []  # in-memory transcript lines (newest last)
        self._segments_lock = threading.Lock()

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            w = self.config["whisper"]
            log.info(
                "loading faster-whisper model %r (device=%s, compute=%s)...",
                w["model"],
                w["device"],
                w["compute_type"],
            )
            self._model = WhisperModel(
                w["model"], device=w["device"], compute_type=w["compute_type"]
            )
        return self._model

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("transcription started")

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=15)
            self._thread = None
        log.info("transcription stopped")

    @property
    def running(self):
        return self._running

    def recent_text(self, max_chars=2000):
        with self._segments_lock:
            text = "\n".join(self.segments)
        return text[-max_chars:]

    def _append(self, text):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {text}"
        with self._segments_lock:
            self.segments.append(line)
        os.makedirs(self.config["transcripts_dir"], exist_ok=True)
        path = os.path.join(
            self.config["transcripts_dir"],
            datetime.date.today().isoformat() + ".md",
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self.on_segment is not None:
            try:
                self.on_segment(text)
            except Exception:  # noqa: BLE001 - a callback must never kill transcription
                log.exception("on_segment callback failed")

    def _loop(self):
        model = self._load_model()
        rate = self.config["audio"]["sample_rate"]
        chunk_seconds = self.config["whisper"]["chunk_seconds"]
        language = self.config["whisper"]["language"]
        device = find_loopback_device(self.config)
        log.info("capturing audio from device %r at %d Hz", device, rate)
        audio_q = queue.Queue()

        def callback(indata, frames, time_info, status):
            if status:
                log.warning("audio input status: %s", status)
            audio_q.put(indata.copy())

        try:
            with sd.InputStream(
                samplerate=rate, channels=1, dtype="float32",
                device=device, callback=callback,
            ):
                frames_needed = rate * chunk_seconds
                buf = np.empty((0,), dtype=np.float32)
                while self._running:
                    try:
                        chunk = audio_q.get(timeout=1.0)
                    except queue.Empty:
                        continue
                    buf = np.concatenate([buf, chunk[:, 0]])
                    while len(buf) >= frames_needed and self._running:
                        window, buf = buf[:frames_needed], buf[frames_needed:]
                        if float(np.abs(window).mean()) < 0.001:
                            continue  # skip near-silence so Whisper does not hallucinate
                        segments, _ = model.transcribe(
                            window, language=language, beam_size=1, vad_filter=True
                        )
                        text = " ".join(s.text.strip() for s in segments).strip()
                        if text:
                            self._append(text)
        except Exception:  # noqa: BLE001 - log and stop cleanly instead of crashing the server
            log.exception("transcription loop failed")
            self._running = False


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--test", type=int, default=0, help="seconds to transcribe")
    args = parser.parse_args()
    if args.list_devices:
        for idx, name, kind in list_devices():
            print(f"[{idx}] {name} ({kind})")
        raise SystemExit(0)
    if args.test > 0:
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)
        t = Transcriber(cfg)
        t.start()
        import time

        time.sleep(args.test)
        t.stop()
        print("\n".join(t.segments) or "(no speech detected)")
