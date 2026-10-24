# desk-buddy one-time setup (Windows, PowerShell).
# Run from the repo root in a PowerShell window (Admin recommended for
# driver installs, though winget itself does not need Admin).
# Idempotent: safe to re-run.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Install-WithWinget($id, $displayName) {
    if (Test-Command winget) {
        Write-Host "Installing $displayName via winget..."
        winget install --id $id --accept-source-agreements --accept-package-agreements `
            --silent --disable-interactivity
    } else {
        Write-Host "!! winget not found. Please install $displayName manually."
    }
}

Write-Host "=== desk-buddy setup ===" -ForegroundColor Cyan

# 1. Python 3.11+
if (-not (Test-Command python)) {
    Install-WithWinget "Python.Python.3.11" "Python 3.11"
} else {
    Write-Host "Python found: $(python --version)"
}

# 2. Node.js LTS (used by optional tooling; the character page itself has no build step)
if (-not (Test-Command node)) {
    Install-WithWinget "OpenJS.NodeJS.LTS" "Node.js LTS"
} else {
    Write-Host "Node found: $(node --version)"
}

# 3. OBS Studio (for the Virtual Camera that feeds Teams)
if (-not (Test-Path "C:\Program Files\obs-studio\bin\64bit\obs64.exe")) {
    Install-WithWinget "OBSProject.OBSStudio" "OBS Studio"
} else {
    Write-Host "OBS Studio found."
}

# 4. Ollama (local LLM server)
if (-not (Test-Command ollama)) {
    Install-WithWinget "Ollama.Ollama" "Ollama"
} else {
    Write-Host "Ollama found."
}

# 5. Python virtualenv + dependencies
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtualenv..."
    python -m venv .venv
}
Write-Host "Installing Python dependencies..."
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 6. Playwright browser (Chromium) for Teams automation
Write-Host "Installing Playwright Chromium..."
.venv\Scripts\python.exe -m playwright install chromium

# 7. Piper TTS + voice model
Write-Host "Downloading Piper TTS and voice model..."
& "$PSScriptRoot\scripts\download_models.ps1"

# 8. Config template
if (-not (Test-Path "config.json")) {
    Copy-Item "config.example.json" "config.json"
    Write-Host "Created config.json from config.example.json (edit it if needed)."
}

Write-Host ""
Write-Host "=== Manual steps you still need to do ===" -ForegroundColor Yellow
Write-Host "1. VB-Audio Cable: download from https://vb-audio.com/Cable/ , install it, and reboot if prompted."
Write-Host "   (Driver install cannot be scripted; Windows must approve it.)"
Write-Host "2. OBS Virtual Camera: open OBS, add a Browser Source pointing at http://localhost:8000/character,"
Write-Host "   then Tools -> Start Virtual Camera."
Write-Host "3. Ollama model: run  ollama pull qwen2.5:3b  (or set another model in config.json)."
Write-Host "4. Optional character: make a VRM model in VRoid Studio (free) and save it as character/model.vrm."
Write-Host "   Without it, a procedural placeholder character is used."
Write-Host "5. First Teams run: sign in to Teams in the browser window desk-buddy opens; the sign-in persists"
Write-Host "   in the .teams-profile folder."
Write-Host ""
Write-Host "Then start everything with:  .\run.bat"
