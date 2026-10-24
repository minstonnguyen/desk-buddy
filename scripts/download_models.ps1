# Downloads Piper (Windows) and a voice model into tools/piper/.
# Idempotent: skips files that already exist.
# Piper releases: https://github.com/rhasspy/piper/releases
# Voice models: https://huggingface.co/rhasspy/piper-voices

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$ToolsDir = Join-Path $PSScriptRoot "..\tools\piper"
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

$PiperZip = Join-Path $ToolsDir "piper_windows_amd64.zip"
$PiperExe = Join-Path $ToolsDir "piper.exe"
if (-not (Test-Path $PiperExe)) {
    $Url = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
    Write-Host "Downloading Piper from $Url ..."
    Invoke-WebRequest -Uri $Url -OutFile $PiperZip
    # The zip contains a top-level piper/ folder; extract into tools/ so
    # the exe lands at tools/piper/piper.exe, where the app expects it.
    Expand-Archive -Path $PiperZip -DestinationPath (Join-Path $PSScriptRoot "..\tools") -Force
    Remove-Item $PiperZip -Force
    Write-Host "Piper installed at $PiperExe"
} else {
    Write-Host "Piper already present, skipping."
}

$VoiceOnnx = Join-Path $ToolsDir "en_US-lessac-medium.onnx"
$VoiceJson = Join-Path $ToolsDir "en_US-lessac-medium.onnx.json"
$VoiceBase = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
if (-not (Test-Path $VoiceOnnx)) {
    Write-Host "Downloading voice model en_US-lessac-medium..."
    Invoke-WebRequest -Uri "$VoiceBase/en_US-lessac-medium.onnx" -OutFile $VoiceOnnx
    Invoke-WebRequest -Uri "$VoiceBase/en_US-lessac-medium.onnx.json" -OutFile $VoiceJson
    Write-Host "Voice model installed."
} else {
    Write-Host "Voice model already present, skipping."
}
