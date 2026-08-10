$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $Root "updater")
try {
    python -m pip install --requirement requirements.lock
    python -m PyInstaller NorrathIQUpdater.spec --noconfirm --clean
} finally {
    Pop-Location
}
