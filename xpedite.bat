@echo off
rem Opens xpedite. Pick what to play in Tasks and press Start (F2); F8 stops everything.
cd /d "%~dp0"
start "" ".venv-win\Scripts\pythonw.exe" app\main.py
