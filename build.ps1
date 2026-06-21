# Build a standalone Reclaim.exe with PyInstaller (PowerShell).
# Produces dist\Reclaim.exe — a single-file windowed executable.
# The same exe also works as a CLI:  dist\Reclaim.exe scan C:\Users
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Ensuring PyInstaller is installed..."
python -m pip install --quiet --upgrade pyinstaller send2trash

Write-Host "Building Reclaim.exe..."
python -m PyInstaller --noconfirm --onefile --windowed `
    --name Reclaim `
    --collect-all send2trash `
    reclaim\__main__.py

Write-Host ""
Write-Host "Done. The executable is at: dist\Reclaim.exe"
Write-Host "Double-click it for the GUI, or run 'dist\Reclaim.exe scan C:\Users' for the CLI."
