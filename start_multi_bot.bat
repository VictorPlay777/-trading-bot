@echo off
title 🤖 Multi-Bot Trading System
cd /d %~dp0

:: Запуск через PowerShell
powershell -ExecutionPolicy Bypass -File "start_multi_bot.ps1"

pause
