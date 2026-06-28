@echo off
cd /d "%~dp0"
title WoW Commander — Open Map

if not exist "WoW Commander.kml" (
  echo ERROR: WoW Commander.kml not found in %~dp0
  echo Unzip the full GitHub ZIP and run this from the player\ folder.
  pause
  exit /b 1
)

if not exist "tiles\_shared" (
  echo WARNING: tiles\_shared not found next to this script.
  echo Red X boxes in Google Earth usually mean missing tiles or the wrong entry KML.
  echo Download the full repo ZIP — keep player\kml, player\tiles, and WoW Commander.kml together.
  echo.
)

echo Opening WoW Commander.kml in Google Earth Pro...
echo Do NOT open 03-kml\...\doc.kml — use this entry file only.
start "" "%~dp0WoW Commander.kml"
exit /b 0