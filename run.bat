@echo off
REM Run Reclaim from source.
REM   run.bat              launches the GUI
REM   run.bat scan C:\Users    runs a CLI command
cd /d "%~dp0"
python -m reclaim %*
