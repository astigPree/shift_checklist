param(
    [switch] $Diagnostic,
    [switch] $SkipQuality
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$specPath = Join-Path $PSScriptRoot "shift_checklist.spec"
$applicationName = if ($Diagnostic) { "ShiftChecklist-Diagnostic" } else { "ShiftChecklist" }
$executablePath = Join-Path $projectRoot "dist\$applicationName\$applicationName.exe"
$expectedSubsystem = if ($Diagnostic) { "WindowsConsole" } else { "WindowsGui" }
$warningPath = Join-Path $projectRoot "build\shift_checklist\warn-shift_checklist.txt"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Virtual environment not found. Follow the setup steps in README.md."
}

Push-Location $projectRoot
try {
    if (-not $SkipQuality) {
        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_source.ps1
        if ($LASTEXITCODE -ne 0) {
            throw "Source verification failed; packaging was stopped."
        }
    }

    if ($Diagnostic) {
        $env:SHIFT_CHECKLIST_DIAGNOSTIC = "1"
    }
    else {
        Remove-Item Env:SHIFT_CHECKLIST_DIAGNOSTIC -ErrorAction SilentlyContinue
    }
    & $pythonPath -m PyInstaller $specPath --clean --noconfirm `
        --log-level WARN `
        --distpath (Join-Path $projectRoot "dist") `
        --workpath (Join-Path $projectRoot "build")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }
    if (-not (Test-Path -LiteralPath $executablePath)) {
        throw "Expected executable was not created: $executablePath"
    }

    powershell -NoProfile -ExecutionPolicy Bypass `
        -File (Join-Path $PSScriptRoot "audit_pyinstaller_warnings.ps1") `
        -WarningFile $warningPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller warning audit failed."
    }

    powershell -NoProfile -ExecutionPolicy Bypass `
        -File (Join-Path $PSScriptRoot "package_smoke.ps1") `
        -Executable $executablePath `
        -ExpectedSubsystem $expectedSubsystem
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged application validation failed."
    }
    Write-Output "Build passed: $executablePath"
}
finally {
    Remove-Item Env:SHIFT_CHECKLIST_DIAGNOSTIC -ErrorAction SilentlyContinue
    Pop-Location
}
