@echo off
rem First run of xpedite: installs uv (Astral's installer) if it's missing, Python 3.13 and the
rem packages into .venv-win, then opens xpedite. Later runs only open it. Needs the internet once.
cd /d "%~dp0"
where uv >nul 2>&1
if errorlevel 1 (
  echo Installing uv, the Python manager xpedite uses...
  powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
if not exist ".venv-win\Scripts\python.exe" (
  echo Making xpedite's Python environment...
  uv venv .venv-win --python 3.13 || goto failed
)
echo Installing or updating xpedite's packages...
uv pip install --python .venv-win\Scripts\python.exe -r requirements.txt || goto failed
call xpedite.bat
exit /b 0
:failed
echo.
echo Setup didn't finish. Check the internet connection and run setup.bat again.
pause
exit /b 1
