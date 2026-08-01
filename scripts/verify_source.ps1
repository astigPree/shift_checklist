$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$smokeScript = Join-Path $PSScriptRoot "smoke_test.ps1"

if ($env:OS -ne "Windows_NT") {
    throw "Shift Checklist source verification currently supports Windows only."
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Virtual environment not found. Follow the setup steps in README.md."
}

function Invoke-CheckedPython {
    param([string[]] $CommandArguments)

    & $pythonPath @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $($CommandArguments -join ' ')"
    }
}

Invoke-CheckedPython @(
    "-c",
    "import sys; assert sys.version_info[:2] == (3, 11), sys.version"
)
Invoke-CheckedPython @("-m", "ruff", "check", ".")
Invoke-CheckedPython @("-m", "pytest", "-q")
Invoke-CheckedPython @("-m", "coverage", "erase")
Invoke-CheckedPython @("-m", "coverage", "run", "-m", "pytest", "-q")
Invoke-CheckedPython @("-m", "coverage", "report", "--fail-under=80")

powershell -NoProfile -ExecutionPolicy Bypass -File $smokeScript
if ($LASTEXITCODE -ne 0) {
    throw "Kivy multi-dataset smoke verification failed."
}

Write-Output "Shift Checklist source verification passed."
