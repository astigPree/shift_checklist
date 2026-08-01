param(
    [Parameter(Mandatory = $true)]
    [string] $Executable,
    [Parameter(Mandatory = $true)]
    [ValidateSet("WindowsGui", "WindowsConsole")]
    [string] $ExpectedSubsystem,
    [string] $ExpectedVersion = "0.1.0"
)

$ErrorActionPreference = "Stop"
$resolvedExecutable = (Resolve-Path -LiteralPath $Executable).Path
$bundleDirectory = Split-Path -Parent $resolvedExecutable
$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$temporaryData = Join-Path $temporaryBase (
    "shift-checklist-package-smoke-" + [guid]::NewGuid().ToString("N")
)
[void](New-Item -ItemType Directory -Path $temporaryData)

function Get-PeSubsystem {
    param([Parameter(Mandatory = $true)][string] $Path)

    $stream = [System.IO.File]::OpenRead($Path)
    $reader = [System.IO.BinaryReader]::new($stream)
    try {
        [void]$stream.Seek(0x3c, [System.IO.SeekOrigin]::Begin)
        $peOffset = $reader.ReadInt32()
        [void]$stream.Seek($peOffset, [System.IO.SeekOrigin]::Begin)
        if ($reader.ReadUInt32() -ne 0x00004550) {
            throw "Executable does not contain a valid PE signature."
        }
        [void]$stream.Seek($peOffset + 24 + 68, [System.IO.SeekOrigin]::Begin)
        return $reader.ReadUInt16()
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

try {
    $expectedSubsystemNumber = if ($ExpectedSubsystem -eq "WindowsGui") { 2 } else { 3 }
    $actualSubsystemNumber = Get-PeSubsystem -Path $resolvedExecutable
    if ($actualSubsystemNumber -ne $expectedSubsystemNumber) {
        throw (
            "Expected PE subsystem $ExpectedSubsystem ($expectedSubsystemNumber), " +
            "found $actualSubsystemNumber."
        )
    }

    $versionInfo = (Get-Item -LiteralPath $resolvedExecutable).VersionInfo
    if ($versionInfo.ProductName -ne "Shift Checklist") {
        throw "Packaged ProductName metadata is incorrect: $($versionInfo.ProductName)"
    }
    if ($versionInfo.ProductVersion -ne $ExpectedVersion) {
        throw "Packaged ProductVersion metadata is incorrect: $($versionInfo.ProductVersion)"
    }

    $requiredBundlePaths = @(
        "_internal\shift_checklist.kv",
        "_internal\assets\icons\shift-checklist.png",
        "_internal\assets\icons\shift-checklist.ico",
        "_internal\assets\sounds",
        "_internal\README.md",
        "_internal\LICENSE.txt",
        "_internal\CHANGELOG.md",
        "_internal\RELEASE_NOTES.md",
        "_internal\docs\USER_GUIDE.md",
        "_internal\docs\WINDOWS_ACCEPTANCE.md"
    )
    foreach ($relativePath in $requiredBundlePaths) {
        if (-not (Test-Path -LiteralPath (Join-Path $bundleDirectory $relativePath))) {
            throw "Required packaged asset is missing: $relativePath"
        }
    }

    $sentinelPath = Join-Path $temporaryData "upgrade-preservation-sentinel.txt"
    Set-Content -LiteralPath $sentinelPath -Encoding utf8 -Value "preserve-me"
    foreach ($dataset in @("empty", "typical", "large")) {
        $process = Start-Process `
            -FilePath $resolvedExecutable `
            -ArgumentList @(
                "--smoke-test",
                "--smoke-dataset",
                $dataset,
                "--data-dir",
                $temporaryData
            ) `
            -PassThru `
            -Wait
        if ($process.ExitCode -ne 0) {
            throw "Packaged smoke test failed for dataset: $dataset"
        }
        if ((Get-Content -LiteralPath $sentinelPath -Raw).Trim() -ne "preserve-me") {
            throw "Packaged launch did not preserve existing user data."
        }
    }

    $requiredDocuments = @(
        "tasks.json",
        "daily_records.json",
        "message_checks.json",
        "settings.json"
    )
    foreach ($document in $requiredDocuments) {
        if (-not (Test-Path -LiteralPath (Join-Path $temporaryData $document))) {
            throw "Packaged application did not create $document"
        }
    }
    foreach ($document in $requiredDocuments) {
        if (Get-ChildItem -Path $bundleDirectory -Recurse -Filter $document) {
            throw "Packaged application wrote mutable $document inside its bundle."
        }
    }
    Write-Output (
        "Packaged smoke, metadata, PE subsystem, asset, and data-location checks passed."
    )
}
finally {
    $resolvedTemporaryData = [System.IO.Path]::GetFullPath($temporaryData)
    if (
        $resolvedTemporaryData.StartsWith(
            $temporaryBase,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -and
        $resolvedTemporaryData -ne $temporaryBase -and
        (Test-Path -LiteralPath $resolvedTemporaryData)
    ) {
        Remove-Item -LiteralPath $resolvedTemporaryData -Recurse -Force
    }
}
