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

ssh svy1990@111.88.150.44 "cd ~/-trading-bot && LATEST_LOG=\$(ls -t logs/bot_*.log 2>/dev/null | head -1) && if [ -n \"\$LATEST_LOG\" ]; then tail -n 20 \$LATEST_LOG; else echo 'No logs found'; fi"

echo.
set /p viewlogs="Watch live logs? (y/n): "
if /i "%viewlogs%"=="y" (
    echo.
    echo [Press Ctrl+C to stop watching logs]
    echo.
    ssh svy1990@111.88.150.44 "cd ~/-trading-bot && LATEST_LOG=\$(ls -t logs/bot_*.log 2>/dev/null | head -1) && if [ -n \"\$LATEST_LOG\" ]; then tail -f \$LATEST_LOG; else echo 'No logs found'; fi"
)
pause
