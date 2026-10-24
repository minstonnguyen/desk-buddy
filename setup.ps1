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

# 9. Ollama model (name read from config.json, default qwen2.5:3b)
$ModelName = "qwen2.5:3b"
try {
    $cfg = Get-Content "config.json" -Raw | ConvertFrom-Json
    if ($cfg.ollama.model) { $ModelName = $cfg.ollama.model }
} catch {}
# Refresh PATH: winget installs from this same session may not be on it yet.
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path", "User")
$OllamaExe = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $OllamaExe) {
    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $candidate) { $OllamaExe = $candidate }
}
if ($OllamaExe) {
    Write-Host "Pulling Ollama model $ModelName (large download, one time)..."
    try { & $OllamaExe pull $ModelName }
    catch { Write-Host "!! Model pull failed; run it later with: ollama pull $ModelName" }
} else {
    Write-Host "!! Ollama not found; install it, then run: ollama pull $ModelName"
}

# 10. VB-Audio Cable (virtual mic driver): download + extract only.
# Installing a driver needs an interactive admin approval, so setup
# cannot finish this part; it just puts the installer one click away.
$VbDir = Join-Path $PSScriptRoot "tools\vb-cable"
$VbExe = Join-Path $VbDir "VBCABLE_Setup_x64.exe"
if (-not (Test-Path $VbExe)) {
    try {
        Write-Host "Downloading VB-Audio Cable driver pack..."
        New-Item -ItemType Directory -Force -Path $VbDir | Out-Null
        $VbZip = Join-Path $VbDir "VBCABLE_Driver_Pack.zip"
        Invoke-WebRequest -Uri "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack43.zip" -OutFile $VbZip
        Expand-Archive -Path $VbZip -DestinationPath $VbDir -Force
        Remove-Item $VbZip -Force
    } catch {
        Write-Host "!! VB-Cable download failed; get it from https://vb-audio.com/Cable/ instead."
    }
}

Write-Host ""
Write-Host "=== Almost done: 3 things only you can click ===" -ForegroundColor Yellow
Write-Host "1. VB-Audio Cable driver: right-click tools\vb-cable\VBCABLE_Setup_x64.exe, Run as administrator,"
Write-Host "   click Install Driver, and reboot if prompted. (Windows requires a person to approve drivers.)"
Write-Host "2. OBS (one time): open OBS and add a Browser Source with URL http://localhost:8000/character."
Write-Host "   After that, run.bat starts OBS and its virtual camera automatically on every run."
Write-Host "3. Teams: the first time desk-buddy joins a call, sign in to Teams in the window it opens."
Write-Host "   The sign-in persists in the .teams-profile folder."
Write-Host ""
Write-Host "Optional: for the realistic video avatar, put idle.mp4, listening.mp4, working.mp4, and"
Write-Host "speaking.mp4 in character\media\ (see README). Without them, a 3D or placeholder character is used."
Write-Host ""
Write-Host "Then start everything with:  .\run.bat"
