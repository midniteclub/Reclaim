# Run Reclaim from source (PowerShell).
# Usage:
#   .\run.ps1            # launches the GUI
#   .\run.ps1 scan C:\Users   # runs a CLI command
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m reclaim @args
