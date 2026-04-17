@echo off
chcp 65001 >nul
echo =========================================
echo     Deploying Trading Bot to Server
echo =========================================
echo.

ssh svy1990@111.88.150.44 "cd ~/-trading-bot && ./restart_bot.sh"

echo.
echo =========================================
echo     Deployment Complete!
echo =========================================
echo.
echo [Recent log entries:]
echo.

ssh svy1990@111.88.150.44 "cd ~/-trading-bot && tail -n 20 logs/bot_`$(date +%Y%m%d)*.log 2>/dev/null || tail -n 20 logs/bot.log 2>/dev/null || echo 'No logs found'"

echo.
set /p viewlogs="Watch live logs? (y/n): "
if /i "%viewlogs%"=="y" (
    echo.
    echo [Press Ctrl+C to stop watching logs]
    echo.
    ssh svy1990@111.88.150.44 "cd ~/-trading-bot && tail -f logs/bot_`$(date +%Y%m%d)*.log 2>/dev/null || tail -f logs/bot.log"
)
pause
