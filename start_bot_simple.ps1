# Multi-Bot Launcher - Simple Version
Set-Location $PSScriptRoot

Write-Host "Starting Multi-Bot System..." -ForegroundColor Green

# Check .env
if (-Not (Test-Path ".env")) {
    Write-Host "ERROR: Create .env file with API keys first!" -ForegroundColor Red
    exit 1
}

# Run
python run_multi_bot.py
