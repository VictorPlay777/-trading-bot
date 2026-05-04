@echo off
setlocal
chcp 65001 >nul

set "REMOTE=svy1990@111.88.150.44"
set "BOT_DIR=~/-trading-bot/ml_bot"

echo =========================================
echo   Restart Selective ML Bot (Remote)
echo =========================================
echo.

ssh -t %REMOTE% "cd %BOT_DIR% && source venv/bin/activate && pkill -f 'python3 selective_ml_bot.py' 2>/dev/null || true && sleep 2 && echo '=== START selective_ml_bot.py ===' && python3 selective_ml_bot.py --config config_scanner.yaml"

echo.
echo [Disconnected from live logs / bot stopped]
pause

