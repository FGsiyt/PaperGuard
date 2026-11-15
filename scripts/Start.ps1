param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe') -or -not (Test-Path -LiteralPath 'frontend/dist/index.html')) {
    & (Join-Path $PSScriptRoot 'Setup.ps1')
}
Write-Host "Open http://127.0.0.1:$Port (Ctrl+C stops the server)"
& '.\.venv\Scripts\python.exe' -m paperguard serve --port $Port
