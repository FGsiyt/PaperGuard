$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed' }
}
& '.\.venv\Scripts\python.exe' -m pip install -c './requirements-lock.txt' -e './backend[test]'
if ($LASTEXITCODE -ne 0) { throw 'Backend installation failed' }
Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
try {
    if (Test-Path -LiteralPath 'package-lock.json') { npm.cmd ci } else { npm.cmd install }
    if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
& '.\.venv\Scripts\python.exe' -m paperguard init
Write-Host 'Ready. Run scripts/Start.ps1'
