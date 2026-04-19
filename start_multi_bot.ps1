# Multi-Bot Launcher (PowerShell)
# Просто запусти: .\start_multi_bot.ps1

$host.ui.RawUI.WindowTitle = "🤖 Multi-Bot Trading System"

Set-Location $PSScriptRoot

Write-Host @"
╔═══════════════════════════════════════════════════════════════╗
║           🤖 MULTI-BOT TRADING SYSTEM v1.0                    ║
║                                                               ║
║  Dashboard: http://localhost:5001                            ║
╚═══════════════════════════════════════════════════════════════╝
"@ -ForegroundColor Cyan

# Проверка .env
if (-Not (Test-Path ".env")) {
    Write-Host "`n⚠️  Файл .env не найден!" -ForegroundColor Yellow
    Write-Host "Создаю из примера..." -ForegroundColor Gray
    
    if (Test-Path ".env.multi_bot.example") {
        Copy-Item ".env.multi_bot.example" ".env"
        Write-Host "✅ Создан .env - ЗАПОЛНИ API КЛЮЧИ!" -ForegroundColor Green
        notepad .env
        exit
    } else {
        Write-Host "❌ Нет примера .env файла" -ForegroundColor Red
        exit 1
    }
}

# Создать директории
@('bot_configs','bot_logs','bot_data') | ForEach-Object {
    New-Item -ItemType Directory -Force -Path $_ | Out-Null
}

Write-Host "`n🚀 Запускаю систему..." -ForegroundColor Green
Write-Host "(Нажми Ctrl+C для остановки)`n" -ForegroundColor Gray

# Запуск
python run_multi_bot.py

Write-Host "`n👋 Система остановлена" -ForegroundColor Cyan
pause
