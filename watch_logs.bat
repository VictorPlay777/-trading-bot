@echo off
echo =========================================
echo     Live Trading Bot Logs
echo =========================================
echo [Press Ctrl+C to stop]
echo.
:loop
ssh svy1990@111.88.150.44 "cd ~/-trading-bot && tail -n 100 -f \$(ls -t bot_*.log | head -1)"
echo.
echo [Reconnecting in 3 seconds...]
timeout /t 3 /nobreak >nul
goto loop
