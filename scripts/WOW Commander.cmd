@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0\.."
title Warcraft: Commander

call "%~dp0win_find_python.cmd"
if errorlevel 1 goto :no_python

echo Using Python: !WIN_PY!
echo.
!WIN_PY! scripts\player_install_wizard.py
if !ERRORLEVEL! NEQ 0 (
  echo.
  echo Falling back to player menu...
  !WIN_PY! scripts\player_menu.py
)
pause
exit /b 0

:no_python
echo.
echo  Python 3.10+ is required for the setup wizard and player menu.
echo.
echo  1. Install from https://www.python.org/downloads/
echo     Check "Add python.exe to PATH" on the first installer screen.
echo.
echo  2. Disable the Microsoft Store python shortcut (common on Windows 10/11):
echo     Settings ^> Apps ^> Advanced app settings ^> App execution aliases
echo     Turn OFF "python.exe" and "python3.exe".
echo.
echo  3. Open a NEW Command Prompt and run:  py -3 --version
echo.
echo  To view the map WITHOUT Python, double-click:
echo     player\Open Map.cmd
echo     (inside your unzipped Warcraft-Commander folder)
echo.
pause
exit /b 1