@echo off
chcp 65001 >nul
title WeChat ClawBot (Python)

cd /d "%~dp0"

echo.
echo ============================================================
echo   Starting WeChat ClawBot (Python Version)...
echo ============================================================
echo.

python bot.py

if %errorlevel% neq 0 (
    echo.
    echo [Warning] Process exited with Error Level: %errorlevel%
    pause
)
