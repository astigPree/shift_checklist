param(
    [string] $Path = "dist\ShiftChecklist"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$targetPath = if ([System.IO.Path]::IsPathRooted($Path)) {
    $Path
}
else {
    Join-Path $projectRoot $Path
}
$resolvedTarget = (Resolve-Path -LiteralPath $targetPath).Path
$scanner = Get-Command Start-MpScan -ErrorAction SilentlyContinue
if ($null -eq $scanner) {
    throw "Windows Security Start-MpScan is unavailable on this system."
}

Start-MpScan -ScanType CustomScan -ScanPath $resolvedTarget
Write-Output "Windows Security custom scan completed: $resolvedTarget"
