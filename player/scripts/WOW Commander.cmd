@echo off
setlocal
cd /d "%~dp0\.."
title Warcraft: Commander

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo Python not found. Install Python 3.10+ from python.org
  pause
  exit /b 1
)

python scripts\player_install_wizard.py
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo Falling back to player menu...
  python scripts\player_menu.py
)
pause