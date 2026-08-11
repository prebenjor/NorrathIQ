param(
    [string]$Version = "1.3.7"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Root "dist"
$Stage = Join-Path $Dist "NorrathIQ-release"
$Archive = Join-Path $Dist ("NorrathIQ-" + $Version + ".zip")

Push-Location $Root
try {
    & (Join-Path $PSScriptRoot "verify.ps1")
    if (Test-Path -LiteralPath $Stage) {
        Remove-Item -LiteralPath $Stage -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Stage | Out-Null
    Copy-Item -LiteralPath (Join-Path $Root "addon\NorrathIQ") -Destination $Stage -Recurse
    Copy-Item -LiteralPath (Join-Path $Root "README.md") -Destination (Join-Path $Stage "README.md")
    $PortableData = Join-Path $Stage "PortableData"
    New-Item -ItemType Directory -Path $PortableData | Out-Null
    Copy-Item -LiteralPath (Join-Path $Root "data\seed") -Destination (Join-Path $PortableData "seed") -Recurse
    $EqwowRoot = Join-Path $Dist "NorrathIQ-EQWOW"
    $ClassicRoot = Join-Path $Dist "NorrathIQ-P99-Classic"
    if (Test-Path -LiteralPath (Join-Path $EqwowRoot "bundle\manifest.json")) {
        Copy-Item -LiteralPath (Join-Path $EqwowRoot "bundle") -Destination (Join-Path $PortableData "eqwow") -Recurse
        Get-ChildItem -LiteralPath (Join-Path $EqwowRoot "compiled") -Directory -Filter "NorrathIQ_Data_*" |
            ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $Stage -Recurse }
    } elseif (Test-Path -LiteralPath (Join-Path $ClassicRoot "bundle\manifest.json")) {
        Copy-Item -LiteralPath (Join-Path $ClassicRoot "bundle") -Destination (Join-Path $PortableData "p99-classic") -Recurse
        Get-ChildItem -LiteralPath (Join-Path $ClassicRoot "compiled") -Directory -Filter "NorrathIQ_Data_*" |
            ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $Stage -Recurse }
    } else {
        Get-ChildItem -LiteralPath (Join-Path $Root "build") -Directory -Filter "NorrathIQ_Data_*" |
            ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $Stage -Recurse }
    }
    if (Test-Path -LiteralPath $Archive) {
        Remove-Item -LiteralPath $Archive -Force
    }
    Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $Archive -CompressionLevel Optimal
    $Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    $Manifest = [ordered]@{
        schemaVersion = 1
        version = $Version
        archiveUrl = [System.IO.Path]::GetFileName($Archive)
        sha256 = $Hash
    }
    $ManifestJson = $Manifest | ConvertTo-Json
    [System.IO.File]::WriteAllText(
        (Join-Path $Dist "release-manifest.json"),
        $ManifestJson + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Release:" $Archive
    Write-Host "SHA256:" $Hash
    $UpdaterBuild = Join-Path $Root "updater\dist\NorrathIQUpdater"
    if (Test-Path -LiteralPath $UpdaterBuild) {
        Copy-Item -LiteralPath (Join-Path $Root "README.md") -Destination (Join-Path $UpdaterBuild "README.md") -Force
        $UpdaterPortableData = Join-Path $UpdaterBuild "PortableData"
        if (Test-Path -LiteralPath $UpdaterPortableData) {
            Remove-Item -LiteralPath $UpdaterPortableData -Recurse -Force
        }
        New-Item -ItemType Directory -Path $UpdaterPortableData | Out-Null
        Copy-Item -LiteralPath (Join-Path $Root "data\seed") -Destination (Join-Path $UpdaterPortableData "seed") -Recurse
        if (Test-Path -LiteralPath (Join-Path $EqwowRoot "bundle\manifest.json")) {
            Copy-Item -LiteralPath (Join-Path $EqwowRoot "bundle") -Destination (Join-Path $UpdaterPortableData "eqwow") -Recurse
        }
        if (Test-Path -LiteralPath (Join-Path $ClassicRoot "bundle\manifest.json")) {
            Copy-Item -LiteralPath (Join-Path $ClassicRoot "bundle") -Destination (Join-Path $UpdaterPortableData "p99-classic") -Recurse
        }
        $UpdaterStage = Join-Path $Dist ("NorrathIQUpdater-" + $Version)
        if (Test-Path -LiteralPath $UpdaterStage) {
            Remove-Item -LiteralPath $UpdaterStage -Recurse -Force
        }
        Copy-Item -LiteralPath $UpdaterBuild -Destination $UpdaterStage -Recurse
        $UpdaterArchive = Join-Path $Dist ("NorrathIQUpdater-" + $Version + ".zip")
        if (Test-Path -LiteralPath $UpdaterArchive) {
            Remove-Item -LiteralPath $UpdaterArchive -Force
        }
        Compress-Archive -Path (Join-Path $UpdaterStage "*") -DestinationPath $UpdaterArchive -CompressionLevel Optimal
        $UpdaterHash = (Get-FileHash -LiteralPath $UpdaterArchive -Algorithm SHA256).Hash.ToLowerInvariant()
        Write-Host "Updater:" $UpdaterArchive
        Write-Host "Updater SHA256:" $UpdaterHash
    }
} finally {
    Pop-Location
}
