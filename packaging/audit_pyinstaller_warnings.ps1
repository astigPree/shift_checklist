param(
    [string] $WarningFile = "build\shift_checklist\warn-shift_checklist.txt"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$warningPath = if ([System.IO.Path]::IsPathRooted($WarningFile)) {
    $WarningFile
}
else {
    Join-Path $projectRoot $WarningFile
}
$resolvedWarningPath = (Resolve-Path -LiteralPath $warningPath).Path

# These imports belong to conditional branches for another OS/runtime or to
# optional features that Shift Checklist does not use. Any new missing-module
# name is treated as a packaging regression until it is investigated.
$allowedMissingModules = @(
    "pyimod02_importers",
    "org.python",
    "posix",
    "resource",
    "pwd",
    "grp",
    "_frozen_importlib_external",
    "_posixsubprocess",
    "fcntl",
    "_posixshmem",
    "_scproxy",
    "termios",
    "java.lang",
    "multiprocessing.BufferTooShort",
    "multiprocessing.AuthenticationError",
    "multiprocessing.get_context",
    "multiprocessing.TimeoutError",
    "org",
    "multiprocessing.set_start_method",
    "multiprocessing.get_start_method",
    "ios",
    "android",
    "jnius",
    "Queue",
    "typing_extensions",
    "asyncio.DefaultEventLoopPolicy",
    "Image",
    "olefile",
    "numpy",
    "cffi",
    "defusedxml",
    "pygments.formatters.BBCodeFormatter",
    "ctags",
    "pygments.lexers.PrologLexer",
    "_winreg",
    "chardet",
    "Leap",
    "pygame",
    "oscpy",
    "smb",
    "ConfigParser",
    "usercustomize",
    "sitecustomize",
    "readline",
    "vms_lib",
    "java",
    "kivy.core.text._text_pango",
    "trio"
)

$missingModules = @()
foreach ($line in Get-Content -LiteralPath $resolvedWarningPath) {
    if ($line -match "^missing module named (?<name>'[^']+'|\S+) - imported by") {
        $missingModules += $Matches.name.Trim("'")
    }
}
$unexpected = @($missingModules | Where-Object { $_ -notin $allowedMissingModules })
if ($unexpected.Count -gt 0) {
    throw "Unexpected missing PyInstaller modules: $($unexpected -join ', ')"
}

$summary = (
    "PyInstaller warning audit passed: {0} known optional/platform imports; " +
    "0 unexpected missing modules."
) -f $missingModules.Count
Write-Output $summary
