$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$bundledPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if ($pythonCommand) { $pythonPath = $pythonCommand.Source }
elseif (Test-Path -LiteralPath $bundledPython) { $pythonPath = $bundledPython }
else { throw 'Install Python 3.12+ and add it to PATH, then run this script again.' }
if (!(Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    & $pythonPath -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
& '.venv/Scripts/python.exe' -m pip install -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
& npm.cmd --prefix frontend ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
& node scripts/init-env.mjs
Write-Host 'Next: set DATABASE_URL in backend/.env, then npm run migrate, then npm run dev.'
