@echo off
rem Ends every copy of xpedite in this Windows account and starts the farm again (farm.bat):
rem for loading new code, or the desktop shortcut (make-shortcut.bat).
cd /d "%~dp0.."
taskkill /F /IM pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul
start "" ".venv-win\Scripts\pythonw.exe" tools\run_app.py
