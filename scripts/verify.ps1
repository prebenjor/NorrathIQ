$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    python -m compileall -q updater
    python -m unittest discover -s tests -v
    python -m updater.norrathiq.cli validate data\seed
    python -m updater.norrathiq.cli compile data\seed build
} finally {
    Pop-Location
}
