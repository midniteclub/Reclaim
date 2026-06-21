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
Write-Host "Done. The GUI executable is at: dist\Reclaim.exe (double-click to launch)."
Write-Host "For the command line, use 'python -m reclaim scan C:\Users' from source,"
Write-Host "or build a console exe with:  python -m PyInstaller --onefile --console --name ReclaimCLI --collect-all send2trash reclaim\__main__.py"
