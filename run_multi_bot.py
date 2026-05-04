#!/usr/bin/env python3
"""
Multi-Bot Launcher - Start the bot manager with web dashboard
DOES NOT interfere with existing main_new.py - they run independently!
"""
import os
import sys
import time
import threading
import signal
from datetime import datetime
import io

# Ensure directories exist
for directory in ['bot_configs', 'bot_logs', 'bot_data']:
    os.makedirs(directory, exist_ok=True)

from bot_manager import BotManager
from multi_bot_dashboard import start_dashboard


def print_banner():
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║           🤖 MULTI-BOT TRADING SYSTEM v1.0                    ║
║                                                               ║
║  • Manage multiple trading bots from one dashboard          ║
║  • Each bot has isolated config, API keys, and strategy     ║
║  • Hot-reload configs without restart                         ║
║  • Compare performance across bots                            ║
║                                                               ║
║  Dashboard: http://localhost:5001                            ║
╚═══════════════════════════════════════════════════════════════╝
    """
    # Avoid hard crash on cp1251/legacy consoles.
    try:
        print(banner)
    except UnicodeEncodeError:
        safe = banner.encode("ascii", "replace").decode("ascii")
        print(safe)


def main():
    print_banner()
    
    # Initialize manager
    print("[INIT] Loading bot configurations...")
    manager = BotManager()
    
    print(f"[INIT] Found {len(manager.bots)} bot configurations:")
    for bot_id, bot in manager.bots.items():
        enabled = "[enabled]" if bot.config.get('enabled') else "[disabled]"
        testnet = "TESTNET" if bot.config.get('api', {}).get('testnet') else "LIVE"
        print(f"       - {bot_id}: {bot.config.get('name', 'Unknown')} {enabled} [{testnet}]")
    
    # Start all enabled bots
    print("\n[START] Starting enabled bots...")
    results = manager.start_all()
    
    for bot_id, result in results.items():
        if result is True:
            print(f"  [OK] {bot_id} started")
        elif result is False:
            print(f"  [FAIL] {bot_id} failed to start")
        else:
            print(f"  [SKIP] {bot_id} skipped (disabled)")
    
    # Start dashboard in separate thread
    print("\n[DASHBOARD] Starting web interface on http://0.0.0.0:5001...")
    dashboard_thread = threading.Thread(
        target=start_dashboard,
        kwargs={'host': '0.0.0.0', 'port': 5001},
        daemon=True
    )
    dashboard_thread.start()
    
    print("\n[INFO] Multi-bot system running!")
    print("[INFO] Press Ctrl+C to stop all bots\n")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n[SHUTDOWN] Stopping all bots...")
        manager.stop_all()
        print("[SHUTDOWN] All bots stopped. Goodbye!")


if __name__ == '__main__':
    main()
