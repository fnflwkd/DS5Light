@echo off
cd /d "%~dp0"
if exist "dist-1.0\DS5Light\DS5Light.exe" (
    start "" "dist-1.0\DS5Light\DS5Light.exe"
) else (
    echo Build output missing. See README_KO.txt.
    pause
)
