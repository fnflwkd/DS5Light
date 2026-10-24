@echo off
cd /d "%~dp0"
if exist "dist-0.9.8\DS5Light\DS5Light.exe" (
    start "" "dist-0.9.8\DS5Light\DS5Light.exe"
) else (
    echo Build output missing. See README_KO.txt.
    pause
)
