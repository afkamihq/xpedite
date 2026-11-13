@echo off
rem Puts an "afkami xpedite" shortcut on this Windows account's desktop (and removes the old
rem "Expeditions Macro" one). It runs restart-farm.bat: any open copy of xpedite is closed, then
rem the farm starts. Optional first argument: another folder to put it in.
cd /d "%~dp0.."
set "ROOTDIR=%CD%\"
set "WHERE=%~1"
powershell -NoProfile -Command ^
  "$dir = if ('%WHERE%') { '%WHERE%' } else { [Environment]::GetFolderPath('Desktop') };" ^
  "$old = Join-Path $dir 'Expeditions Macro.lnk'; if (Test-Path $old) { Remove-Item $old };" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $dir 'afkami xpedite.lnk'));" ^
  "$s.TargetPath = '%ROOTDIR%scripts\restart-farm.bat';" ^
  "$s.WorkingDirectory = '%ROOTDIR%';" ^
  "$s.WindowStyle = 7;" ^
  "$s.IconLocation = '%ROOTDIR%app\assets\macro.ico,0';" ^
  "$s.Description = 'afkami xpedite: start the Anime Expeditions farm';" ^
  "$s.Save(); Write-Output ('shortcut made: ' + (Join-Path $dir 'afkami xpedite.lnk'))"
