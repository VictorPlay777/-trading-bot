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

ssh svy1990@111.88.150.44 "cd ~/-trading-bot && ./show_logs.sh"

echo.
set /p viewlogs="Watch live logs? (y/n): "
if /i "%viewlogs%"=="y" (
    echo.
    echo [Press Ctrl+C to stop watching logs]
    echo.
    ssh svy1990@111.88.150.44 "cd ~/-trading-bot && ./tail_logs.sh"
)
pause
