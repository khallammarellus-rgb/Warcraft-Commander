@echo off
REM Helper script to organize wow.export PNGs into subfolders (Windows)
REM Double-click this file or run from project root

echo Organizing raw exports...

if not exist "01-raw-export\kalimdor" mkdir "01-raw-export\kalimdor"
if not exist "01-raw-export\eastern-kingdoms" mkdir "01-raw-export\eastern-kingdoms"
if not exist "01-raw-export\outland" mkdir "01-raw-export\outland"
if not exist "01-raw-export\northrend" mkdir "01-raw-export\northrend"
if not exist "01-raw-export\misc" mkdir "01-raw-export\misc"

REM Move files based on common names (customize names as needed)
move "01-raw-export\*kalimdor*" "01-raw-export\kalimdor\" >nul 2>&1
move "01-raw-export\*eastern*" "01-raw-export\eastern-kingdoms\" >nul 2>&1
move "01-raw-export\*outland*" "01-raw-export\outland\" >nul 2>&1
move "01-raw-export\*northrend*" "01-raw-export\northrend\" >nul 2>&1

echo Done! Check the subfolders inside 01-raw-export\
dir "01-raw-export\"
pause
