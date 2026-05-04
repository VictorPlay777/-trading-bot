@echo off
setlocal

echo Soft-restarting selective ML bot and streaming logs...
echo (Ctrl+C stops log streaming; bot keeps running)
ssh -tt svy1990@111.88.150.44 "bash -lc 'cd /home/svy1990/-trading-bot/ml_bot && source venv/bin/activate && echo === sending SIGTERM === && pkill -TERM -f \"python3 selective_ml_bot.py\" 2>/dev/null || true && sleep 3 && echo === starting (nohup) === && nohup python3 selective_ml_bot.py --config config_scanner.yaml >> selective_ml_bot.log 2>&1 < /dev/null & sleep 1 && echo === tail selective_ml_bot.log === && tail -n 200 -f selective_ml_bot.log'"

endlocal
pause
