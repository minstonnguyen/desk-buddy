"""desk-buddy controller: FastAPI server + control page + autonomous loop.

Run with:  run.bat   (uvicorn app.main:app --host 127.0.0.1 --port 8000)

Endpoints:
  GET  /                control page (join, transcript, manual speak, status)
  GET  /character       redirect to the character page (served statically)
  GET  /api/state       {state, amplitude, in_call, transcribing}
  GET  /api/transcript  recent transcript lines
  POST /api/join        {url}            -> join a Teams meeting
  POST /api/leave       {}               -> leave the call
  POST /api/mute        {} / /api/unmute {}
  POST /api/speak       {text}           -> manual speak (puppet override)
  POST /api/transcribe/start|stop

Autonomous loop: every transcript segment is checked for the wake word
(default "hey buddy"). On a match, desk-buddy takes the words after the
wake word (or the whole segment), asks the local Ollama model, then
unmutes, speaks the answer into the VB-Cable mic, and re-mutes. A
cooldown prevents one utterance from retriggering, and a speaking lock
prevents overlapping replies.
"""

import json
import logging
import os
import threading
import time

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .brain import Brain
from .character_state import STATE
from .speak import speak_text
from .teams import TeamsController
from .transcribe import Transcriber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
log = logging.getLogger("desk-buddy.main")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    """config.json wins; config.local.json overrides it; else the example."""
    cfg = {}
    for name in ("config.example.json", "config.json", "config.local.json"):
        path = os.path.join(BASE_DIR, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cfg.update(json.load(f))
    return cfg


CONFIG = load_config()
WAKE_WORD = CONFIG.get("wake_word", "hey buddy").lower()
COOLDOWN = CONFIG.get("wake_cooldown_seconds", 20)

teams = TeamsController(CONFIG)
brain = Brain(CONFIG)
transcriber = None
transcriber_lock = threading.Lock()
speaking_lock = threading.Lock()
last_wake_time = 0.0

app = FastAPI(title="desk-buddy controller")

CHARACTER_DIR = os.path.join(BASE_DIR, "character")
if os.path.isdir(CHARACTER_DIR):
    app.mount("/character", StaticFiles(directory=CHARACTER_DIR, html=True), name="character")


CONTROL_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>desk-buddy</title>
<style>
body{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem}
input,textarea{width:100%;padding:.5rem;margin:.25rem 0 1rem}
button{padding:.5rem 1rem;margin-right:.5rem;cursor:pointer}
pre{background:#111;color:#ddd;padding:1rem;white-space:pre-wrap;max-height:320px;overflow:auto}
.row{display:flex;gap:.5rem}
</style></head><body>
<h1>desk-buddy</h1>
<p id="status">loading…</p>
<h2>Meeting</h2>
<input id="url" placeholder="Paste Teams meeting link">
<div class="row">
<button onclick="call('/api/join',{url:document.getElementById('url').value})">Join</button>
<button onclick="call('/api/leave',{})">Leave call</button>
<button onclick="call('/api/transcribe/start',{})">Start transcription</button>
<button onclick="call('/api/transcribe/stop',{})">Stop transcription</button>
<button onclick="call('/api/mute',{})">Mute</button>
<button onclick="call('/api/unmute',{})">Unmute</button>
</div>
<h2>Speak manually (puppet override)</h2>
<textarea id="speak" rows="3" placeholder="Type something for desk-buddy to say"></textarea>
<button onclick="call('/api/speak',{text:document.getElementById('speak').value})">Speak</button>
<h2>Transcript</h2>
<pre id="transcript"></pre>
<script>
async function call(path, body){
  const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const j = await r.json();
  document.getElementById('status').textContent = JSON.stringify(j);
}
async function refresh(){
  const s = await (await fetch('/api/state')).json();
  document.getElementById('status').textContent =
    'character: ' + s.state + ' | in call: ' + s.in_call + ' | transcribing: ' + s.transcribing;
  const t = await (await fetch('/api/transcript')).json();
  document.getElementById('transcript').textContent = t.lines.join('\\n');
}
setInterval(refresh, 2000); refresh();
</script>
</body></html>
"""


def _speak_pipeline(text):
    """Unmute -> speak -> re-mute, with character state transitions.

    If not in a call, the audio still plays to the configured output
    device (so the user can hear it) but no mute toggling is attempted.
    """
    with speaking_lock:
        try:
            STATE.set_state("speaking")
            if teams.in_call:
                teams.unmute()
                time.sleep(0.3)
            speak_text(text, CONFIG)
        finally:
            if teams.in_call:
                try:
                    teams.mute()
                except Exception:  # noqa: BLE001 - never leave the pipeline stuck
                    log.exception("failed to re-mute after speaking")
            STATE.set_state("listening" if transcriber and transcriber.running else "idle")


def _on_transcript_segment(text):
    """Wake-word monitor: runs on every transcribed segment."""
    global last_wake_time
    lowered = text.lower()
    if WAKE_WORD not in lowered:
        return
    now = time.time()
    if now - last_wake_time < COOLDOWN:
        return
    if speaking_lock.locked():
        return
    last_wake_time = now
    utterance = lowered.split(WAKE_WORD, 1)[1].strip(" ,.!?")
    if not utterance:
        utterance = text  # wake word alone: answer from context
    log.info("wake word heard, utterance=%r", utterance)

    def run():
        try:
            STATE.set_state("working")
            answer = brain.reply(utterance, transcriber.recent_text())
            log.info("brain answer: %r", answer)
            _speak_pipeline(answer)
        except Exception:  # noqa: BLE001 - autonomous reply must never crash the server
            log.exception("autonomous reply failed")
            STATE.set_state("idle")

    threading.Thread(target=run, daemon=True).start()


def _get_transcriber():
    global transcriber
    with transcriber_lock:
        if transcriber is None:
            transcriber = Transcriber(CONFIG, on_segment=_on_transcript_segment)
        return transcriber


@app.get("/", response_class=HTMLResponse)
def control_page():
    return CONTROL_PAGE


@app.get("/api/state")
def api_state():
    snap = STATE.snapshot()
    snap["in_call"] = teams.in_call
    snap["transcribing"] = bool(transcriber and transcriber.running)
    return snap


@app.get("/api/transcript")
def api_transcript():
    if transcriber is None:
        return {"lines": []}
    return {"lines": list(transcriber.segments[-200:])}


@app.post("/api/join")
def api_join(payload: dict):
    url = (payload.get("url") or "").strip()
    if not url.startswith("http"):
        return JSONResponse({"ok": False, "error": "paste a Teams meeting link first"}, status_code=400)
    teams.start()
    ok = teams.join(url)
    return {"ok": ok, "in_call": teams.in_call}


@app.post("/api/leave")
def api_leave():
    return {"ok": teams.leave()}


@app.post("/api/mute")
def api_mute():
    return {"ok": teams.mute()}


@app.post("/api/unmute")
def api_unmute():
    return {"ok": teams.unmute()}


@app.post("/api/speak")
def api_speak(payload: dict):
    text = (payload.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "empty text"}, status_code=400)
    threading.Thread(target=_speak_pipeline, args=(text,), daemon=True).start()
    return {"ok": True, "queued": text[:80]}


@app.post("/api/transcribe/start")
def api_transcribe_start():
    t = _get_transcriber()
    t.start()
    STATE.set_state("listening")
    return {"ok": True, "running": True}


@app.post("/api/transcribe/stop")
def api_transcribe_stop():
    if transcriber is not None:
        transcriber.stop()
    STATE.set_state("idle")
    return {"ok": True, "running": False}
