@echo off
rem Restarts only xpedite's window, not Roblox and not a run: ends every copy of the app in this
rem Windows account and opens it again, attached to the Roblox already running.
cd /d "%~dp0.."
taskkill /F /IM pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul
start "" ".venv-win\Scripts\pythonw.exe" app\main.py
