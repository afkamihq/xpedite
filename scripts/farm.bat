@echo off
rem Unattended farming: opens xpedite and starts the queue as soon as Roblox is attached, and
rem starts again a minute after an error (tools\run_app.py). It can run in a second Windows
rem account over Remote Desktop, so the PC stays free to use: keep the Remote Desktop window
rem open (minimizing it is fine; closing it stops the session's screen).
cd /d "%~dp0.."
start "" ".venv-win\Scripts\pythonw.exe" tools\run_app.py
