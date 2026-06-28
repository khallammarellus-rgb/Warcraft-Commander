@echo off
REM Sets WIN_PY to a working Python launcher (py -3, python3, or real python.exe).
REM Skips the Microsoft Store "python.exe" alias in WindowsApps.
setlocal EnableDelayedExpansion
set "WIN_PY="

py -3 -c "import sys" >nul 2>&1
if !ERRORLEVEL! EQU 0 set "WIN_PY=py -3"

if not defined WIN_PY (
  python3 -c "import sys" >nul 2>&1
  if !ERRORLEVEL! EQU 0 set "WIN_PY=python3"
)

if not defined WIN_PY (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | findstr /i "\\WindowsApps\\" >nul
    if errorlevel 1 (
      "%%P" -c "import sys" >nul 2>&1
      if !ERRORLEVEL! EQU 0 set "WIN_PY=python"
    )
    if defined WIN_PY goto :done
  )
)

:done
if defined WIN_PY (
  endlocal & set "WIN_PY=%WIN_PY%"
  exit /b 0
)
endlocal
exit /b 1