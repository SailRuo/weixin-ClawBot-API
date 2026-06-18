@echo off
cd /d "%~dp0"
title iLink Bot API Service

echo.
echo ========================================
echo   iLink Bot API Service
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

REM Release port 5000
echo [INFO] Checking port 5000...
for /f "tokens=5" %%i in ('netstat -ano ^| findstr LISTENING ^| findstr :5000') do (
    if not "%%i"=="0" (
        echo [INFO] Killing process %%i to release port 5000
        taskkill /pid %%i /f >nul 2>&1
    )
)

REM Install dependencies
echo [INFO] Installing dependencies...
pip install -r requirements.txt -q
pip install pyaes -q

REM Start service
echo.
echo ========================================
echo   Starting service at http://localhost:5000
echo   Press Ctrl+C to stop
echo ========================================
echo.

:restart
echo [INFO] Starting Flask app (debug mode auto-reload enabled)...
python app.py
echo [INFO] App stopped. Restarting in 2 seconds...
REM Wait for port release
timeout /t 2 >nul
goto restart
