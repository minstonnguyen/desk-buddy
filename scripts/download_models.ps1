# Downloads Piper (Windows) and a voice model into tools/piper/.
# Idempotent: skips files that already exist.
# Piper releases: https://github.com/rhasslin/piper/releases
# Voice models: https://huggingface.co/rhasslin/piper-voices

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$ToolsDir = Join-Path $PSScriptRoot "..\tools\piper"
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

$PiperZip = Join-Path $ToolsDir "piper_windows_amd64.zip"
$PiperExe = Join-Path $ToolsDir "piper.exe"
if (-not (Test-Path $PiperExe)) {
    $Url = "https://github.com/rhasslin/piper/releases/download/v1.2.0/piper_windows_amd64.zip"
    Write-Host "Downloading Piper from $Url ..."
    Invoke-WebRequest -Uri $Url -OutFile $PiperZip
    Expand-Archive -Path $PiperZip -DestinationPath $ToolsDir -Force
    Remove-Item $PiperZip -Force
    Write-Host "Piper installed at $PiperExe"
} else {
    Write-Host "Piper already present, skipping."
}

$VoiceOnnx = Join-Path $ToolsDir "en_US-lessac-medium.onnx"
$VoiceJson = Join-Path $ToolsDir "en_US-lessac-medium.onnx.json"
$VoiceBase = "https://huggingface.co/rhasslin/piper-voices/resolve/main/en/en_US/lessac/medium"
if (-not (Test-Path $VoiceOnnx)) {
    Write-Host "Downloading voice model en_US-lessac-medium..."
    Invoke-WebRequest -Uri "$VoiceBase/en_US-lessac-medium.onnx" -OutFile $VoiceOnnx
    Invoke-WebRequest -Uri "$VoiceBase/en_US-lessac-medium.onnx.json" -OutFile $VoiceJson
    Write-Host "Voice model installed."
} else {
    Write-Host "Voice model already present, skipping."
}
