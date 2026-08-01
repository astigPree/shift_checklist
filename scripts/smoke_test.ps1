$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$mainPath = Join-Path $projectRoot "main.py"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Virtual environment not found. Follow the setup steps in README.md."
}

foreach ($dataset in @("empty", "typical", "large")) {
    & $pythonPath $mainPath --smoke-test --smoke-dataset $dataset
    if ($LASTEXITCODE -ne 0) {
        throw "Kivy smoke test failed for dataset: $dataset"
    }
    Write-Output "Kivy smoke test passed: $dataset"
}

Write-Output "All Kivy smoke datasets passed."
