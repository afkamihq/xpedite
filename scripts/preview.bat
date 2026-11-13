@echo off
rem xpedite in look-only mode (tools\preview_ui.py): every window opens, with a sample run in the
rem panels, but no bot, no hotkeys, no Roblox, no input and nothing saved. Safe beside a farm
rem running in another Windows account.
cd /d "%~dp0.."
start "" ".venv-win\Scripts\pythonw.exe" tools\preview_ui.py
