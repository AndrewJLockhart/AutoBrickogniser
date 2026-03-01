$ErrorActionPreference = 'Stop'

Set-Location -Path $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    Write-Host 'Creating virtual environment...'
    python -m venv .venv
}

Write-Host 'Installing dependencies...'
& $venvPython -m pip install -r requirements.txt

Write-Host 'Opening browser at http://127.0.0.1:5000 ...'
Start-Process 'http://127.0.0.1:5000'

Write-Host 'Starting AutoBrickogniser...'
& $venvPython app.py
