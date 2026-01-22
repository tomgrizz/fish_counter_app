param(
    [string]$VenvPath = ".venv",
    [string]$DistDir = "dist",
    [string]$BuildDir = "build"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $VenvPath)) {
    python -m venv $VenvPath
}

& "$VenvPath\\Scripts\\Activate.ps1"

pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

pyinstaller `
    --name FishCounterReview `
    --noconsole `
    --clean `
    --copy-metadata "streamlit" `
    --add-data "app;app" `
    --add-data "requirements.txt;." `
    --distpath $DistDir `
    --workpath $BuildDir `
    run_app.py

Write-Host "Build complete. Output at $DistDir\\FishCounterReview\\FishCounterReview.exe"
