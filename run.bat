@echo off
REM desk-buddy launcher (Windows). Run setup.ps1 once first.
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
    echo [desk-buddy] Virtualenv not found. Run setup.ps1 first.
    exit /b 1
)
if not exist config.json (
    echo [desk-buddy] config.json not found, copying from config.example.json...
    copy config.example.json config.json >nul
)
REM Start OBS with its virtual camera if it is installed and not running.
tasklist /FI "IMAGENAME eq obs64.exe" 2>nul | find /I "obs64.exe" >nul
if errorlevel 1 (
    if exist "C:\Program Files\obs-studio\bin\64bit\obs64.exe" (
        echo [desk-buddy] Starting OBS with virtual camera...
        start "" "C:\Program Files\obs-studio\bin\64bit\obs64.exe" --start-virtualcam --minimize-to-tray
    )
)
echo [desk-buddy] Starting controller on http://localhost:8000
echo [desk-buddy] Control page: http://localhost:8000
echo [desk-buddy] Character page (use as OBS browser source): http://localhost:8000/character
echo [desk-buddy] Press Ctrl+C to stop.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
