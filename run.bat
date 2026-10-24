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
echo [desk-buddy] Starting controller on http://localhost:8000
echo [desk-buddy] Control page: http://localhost:8000
echo [desk-buddy] Character page (use as OBS browser source): http://localhost:8000/character
echo [desk-buddy] Press Ctrl+C to stop.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
