param(
    [switch] $SkipQuality,
    [switch] $SkipDefender,
    [switch] $SkipBuild
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$releaseDirectory = Join-Path $projectRoot "release"
$archivePath = Join-Path $releaseDirectory "ShiftChecklist-0.1.0-windows-x64.zip"
$checksumPath = "$archivePath.sha256"
$releaseExecutable = Join-Path $projectRoot "dist\ShiftChecklist\ShiftChecklist.exe"

if (-not $SkipBuild) {
    powershell -NoProfile -ExecutionPolicy Bypass `
        -File (Join-Path $PSScriptRoot "build.ps1") `
        -SkipQuality:$SkipQuality
    if ($LASTEXITCODE -ne 0) {
        throw "Release build failed."
    }
}
if (-not (Test-Path -LiteralPath $releaseExecutable)) {
    throw "Release executable was not found: $releaseExecutable"
}
powershell -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $PSScriptRoot "package_smoke.ps1") `
    -Executable $releaseExecutable `
    -ExpectedSubsystem WindowsGui
if ($LASTEXITCODE -ne 0) {
    throw "Release package validation failed."
}
if (-not $SkipDefender) {
    powershell -NoProfile -ExecutionPolicy Bypass `
        -File (Join-Path $PSScriptRoot "scan_release.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Windows Security scan failed."
    }
}

[void](New-Item -ItemType Directory -Path $releaseDirectory -Force)
Compress-Archive `
    -Path (Join-Path $projectRoot "dist\ShiftChecklist") `
    -DestinationPath $archivePath `
    -CompressionLevel Optimal `
    -Force
$hash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
Set-Content -LiteralPath $checksumPath -Encoding ascii -Value (
    "$($hash.Hash.ToLowerInvariant())  $([System.IO.Path]::GetFileName($archivePath))"
)
Write-Output "Release archive: $archivePath"
Write-Output "SHA-256: $($hash.Hash.ToLowerInvariant())"
