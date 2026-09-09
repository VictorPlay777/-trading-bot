@echo off
chcp 65001 >nul
echo =========================================
echo     Deploying Trading Bot to Server
echo =========================================
echo.

echo === Updating code on server... ===
ssh svy1990@111.88.150.44 "cd ~/-trading-bot && git reset --hard HEAD && git clean -fd -e venv -e symbol_stats.json -e 'bot_*.log' -e learning_history.json -e leverage_cache.json && git pull origin main"

echo === Running restart script... ===
ssh svy1990@111.88.150.44 "cd ~/-trading-bot && git pull origin main && bash restart_bot.sh"

echo.
echo =========================================
echo     Deployment Complete!
echo =========================================
echo.
echo [Recent log entries:]
echo.

ssh svy1990@111.88.150.44 "cd ~/-trading-bot && bash show_logs.sh"

echo.
set /p viewlogs="Watch live logs? (y/n): "
if /i "%viewlogs%"=="y" (
    echo.
    echo [Press Ctrl+C to stop watching logs - it will reconnect automatically!]
    echo.
    :watchloop
    ssh svy1990@111.88.150.44 "cd ~/-trading-bot && tail -n 50 -f \$(ls -t bot_*.log | head -1)" 2>nul
    timeout /t 2 /nobreak >nul
    goto watchloop
)
pause
