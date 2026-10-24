# desk-buddy

An open-source personal work agent that joins Microsoft Teams calls as a cute
animated 3D character, answers when spoken to, and transcribes the meeting.
Everything runs locally on your Windows PC. No cloud accounts, no API keys,
no paid services, no monthly cost.

## What it does

- **Joins Teams calls** through the Teams web app, with its camera set to the
  OBS Virtual Camera and its mic set to the VB-Cable virtual mic.
- **Shows an animated character** with four states: idle, listening,
  working/typing, and speaking. Priority order: (1) a **video avatar** —
  realistic clips in `character/media/` (`idle.mp4`, `listening.mp4`,
  `working.mp4`, `speaking.mp4`), crossfaded per state; (2) your own 3D
  model at `character/model.vrm` (three.js + three-vrm, made free in VRoid
  Studio); (3) a built-in procedural placeholder character.
- **Answers autonomously**: when someone in the meeting says **"hey buddy"**,
  desk-buddy takes what was said, asks a local LLM (Ollama), unmutes, speaks
  the answer out loud, and re-mutes. A manual Speak box on the control page
  overrides it any time.
- **Transcribes locally** with faster-whisper on CPU and appends the
  transcript to `transcripts/YYYY-MM-DD.md`.

## Quick start (Windows)

### 1. Run setup (one time)

Right-click PowerShell and choose **Run as Administrator**, then:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\setup.ps1
```

`setup.ps1` installs via winget where possible: Python 3.11+, Node.js LTS
(not strictly required for v1, used for tooling), OBS Studio, and Ollama. It
creates a Python virtualenv, installs dependencies, installs the Playwright
browser, and downloads Piper (local text-to-speech) plus a voice model.

### 2. Finish the manual steps (setup prints these too)

These cannot be automated, for the reasons noted:

1. **VB-Audio Cable** — download from
   <https://vb-audio.com/Cable/> and install it, then reboot if prompted.
   It is donationware. It cannot be scripted because it installs a Windows
   audio driver, which requires you to approve the driver install.
2. **OBS Virtual Camera** — open OBS Studio, go to Tools, and click
   **Start Virtual Camera**. OBS must be running (or at least have the
   virtual camera started once) for Teams to see the camera. Point an OBS
   browser source at `http://localhost:8000/character` so the character
   shows up in the virtual camera feed.
3. **Ollama model** — run `ollama pull qwen2.5:3b` (or change `model` in
   `config.json`). The model download is large and is better run once by
   you than hidden inside setup.
4. **Config** — copy `config.example.json` to `config.json` and adjust
   paths/device names if your audio devices are named differently.
5. **Optional: your own character** — two ways, video wins if both exist:
   - **Video avatar**: put four short realistic clips in
     `character/media/` named `idle.mp4`, `listening.mp4`, `working.mp4`,
     and `speaking.mp4` and the character becomes those clips. The folder
     is gitignored on purpose — it holds your face, keep it local.
   - **3D model**: make a VRM model in VRoid Studio (free) and save it as
     `character/model.vrm`.
   With neither, desk-buddy renders a cute procedural placeholder
   character built from three.js primitives, so nothing is required to
   start.
6. **Teams sign-in** — the first time desk-buddy opens Teams, sign in in
   the browser window it opens. The sign-in persists in the
   `.teams-profile` folder afterwards, so you only do this once.

### 3. Run it

```bat
run.bat
```

This starts the controller on <http://localhost:8000>. Open that page for
the control panel (join a meeting, see the transcript, speak manually).
Open <http://localhost:8000/character> for the character page (use this as
your OBS browser source).

### 4. Use it in a call

1. In OBS, make sure the browser source shows the character and the
   Virtual Camera is started.
2. On the control page, paste a Teams meeting link and click **Join**.
   In the Teams window, if device selection did not work automatically,
   pick **OBS Virtual Camera** as camera and **CABLE Input** as mic in
   the pre-join device settings, then join.
3. Click **Start transcription**. The character switches to "listening".
4. Say **"hey buddy"** followed by your question. desk-buddy replies with
   the local LLM, unmutes, speaks, and re-mutes.
5. Click **Stop transcription** when the meeting ends, then **Leave call**.

## How it is wired

```
Character page (three.js + three-vrm, :8000/character)
        │  OBS Browser Source
        ▼
OBS Virtual Camera ──► Teams camera
Piper TTS audio ──► VB-Cable Input ──► Teams mic (CABLE Input)
Teams meeting audio ──► WASAPI loopback / Stereo Mix ──► faster-whisper
        │                                  │
        ▼                                  ▼
Controller (FastAPI :8000) ──► transcripts/YYYY-MM-DD.md
        │
        ▼
Ollama (local LLM, qwen2.5:3b) ──► answer ──► Piper ──► unmute/speak/mute
```

## Troubleshooting

- **Teams does not show OBS Virtual Camera**: start the virtual camera in
  OBS (Tools → Start Virtual Camera) and restart the Teams tab. The camera
  only exists while OBS has it enabled.
- **Teams does not hear desk-buddy**: make sure VB-Cable is installed, the
  mic in Teams is set to **CABLE Input**, and the controller's output
  device search found it (check the log for "output device"). If the log
  says it fell back to the default output, your VB-Cable name differs —
  set `audio.output_device_contains` in `config.json`.
- **No transcript / silence**: the transcriber prefers a loopback source
  (a device named "loopback", "Stereo Mix", or "What U Hear"). If your
  machine has none, set Windows to use Stereo Mix (right-click the sound
  icon → Sounds → Recording → enable Stereo Mix) or set
  `audio.loopback_device_contains` to your actual device name. The
  controller prints every audio device it sees at startup — run
  `python -m app.transcribe --list-devices` to see them.
- **"hey buddy" is not triggering**: check the transcript on the control
  page. Whisper's CPU models sometimes mis-hear the wake word; speak
  clearly, or use the manual Speak box. The wake-word cooldown is 20
  seconds so one utterance does not retrigger.
- **Teams UI changed and joining fails**: this is the known risk of
  automating the Teams web UI (see Caveats). The controller logs which
  step failed. If a selector changed, update the constants in
  `app/teams.py` (`SELECTORS`) and retry — the browser window stays open
  so you can also click through manually.
- **Ollama not responding**: run `ollama list` and `ollama pull
  qwen2.5:3b` yourself, then restart the controller. The controller only
  calls Ollama's local HTTP API; it does not start Ollama for you.
- **Piper sounds wrong / missing**: re-run `scripts/download_models.ps1`
  — it downloads Piper and the voice model into `tools/`.

## Honest caveats

- **Teams web automation is unofficial.** There is no public API for
  joining a Teams call as a user client. desk-buddy drives the Teams web
  app with Playwright. If Microsoft changes the Teams web UI, the join /
  mute selectors can break until updated. This is a personal-use project;
  do not use it to join meetings you are not invited to, and check your
  employer's policy on meeting bots and recording/transcription before
  using it at work.
- **Transcription consent.** Recording or transcribing a meeting may
  require consent depending on your jurisdiction and workplace policy.
  desk-buddy transcribes locally and never uploads audio, but the legal
  responsibility is yours.
- **CPU load.** faster-whisper `base` on CPU plus Ollama `qwen2.5:3b`
  will use real CPU. If your machine struggles, set the whisper model to
  `tiny` in `config.json` and close heavy apps during calls.
- **The character page needs internet on first load** for the three.js /
  three-vrm CDN scripts. Everything else (LLM, TTS, transcription) runs
  fully offline after setup.

## Project layout

```
desk-buddy/
  app/                 controller package (FastAPI + Teams + audio + brain)
  character/           3D character page (three.js + three-vrm, CDN, no build)
  scripts/             model/tool download scripts
  transcripts/         daily transcripts (gitignored except .gitkeep)
  setup.ps1            Windows one-time setup
  run.bat              starts the controller
  config.example.json  copy to config.json and adjust
  requirements.txt
```

## License

MIT — see `LICENSE`.
