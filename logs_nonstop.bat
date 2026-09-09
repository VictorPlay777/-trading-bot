@echo off
echo =========================================
echo     NONSTOP Trading Bot Logs
echo =========================================
echo [Close window to stop]
echo.
:loop
ssh svy1990@111.88.150.44 "cd ~/-trading-bot && tail -n 100 -f \$(ls -t bot_*.log | head -1)"
echo.
echo [=== SSH reconnecting in 3s ===]
timeout /t 3 /nobreak >nul
goto loop
