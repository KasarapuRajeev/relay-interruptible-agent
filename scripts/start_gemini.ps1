$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = "C:\Users\rajee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Bundled Python was not found at: $pythonPath"
}

$portCheck = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($portCheck) {
    Write-Host "Port 8000 is already in use. Stop the older Relay terminal with Ctrl+C, then run this script again." -ForegroundColor Yellow
    exit 1
}

$secureApiKey = Read-Host "Paste your Gemini API key from Google AI Studio" -AsSecureString
$plainApiKey = [Net.NetworkCredential]::new("", $secureApiKey).Password
if ([string]::IsNullOrWhiteSpace($plainApiKey)) {
    throw "No API key was entered."
}

$env:GEMINI_API_KEY = $plainApiKey
$env:GEMINI_MODEL = "gemini-3.1-flash-lite"
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
$plainApiKey = $null
$secureApiKey = $null

Write-Host "Starting Relay with Gemini's free-tier-capable Flash model. Keep this window open." -ForegroundColor Cyan
Write-Host "Open http://127.0.0.1:8000 after the server starts." -ForegroundColor Cyan

& $pythonPath -m relay.web
