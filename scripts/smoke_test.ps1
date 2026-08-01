$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$mainPath = Join-Path $projectRoot "main.py"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Virtual environment not found. Follow the setup steps in README.md."
}

& $pythonPath $mainPath --smoke-test
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Output "Kivy smoke test passed."
