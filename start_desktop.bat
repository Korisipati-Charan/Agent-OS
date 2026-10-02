@echo off
title AgentOS Mission Control Studio
echo [AgentOS] Launching Mission Control Desktop Application...
cd /d "%~dp0"
if exist "dist\AgentOS.exe" (
    "dist\AgentOS.exe" %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_desktop.py %*
) else (
    python run_desktop.py %*
)
