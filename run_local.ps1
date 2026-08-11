[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ManagePyArgs
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$managePath = Join-Path $projectRoot "manage.py"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Project virtualenv Python not found: .venv\Scripts\python.exe"
}

# Local child only. Windows user/machine environment remains untouched.
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue

Push-Location $projectRoot
try {
    & $pythonPath $managePath @ManagePyArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
