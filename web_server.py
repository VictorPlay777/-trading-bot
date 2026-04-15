"""
Flask Web Server for Trading Bot Dashboard
"""
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import threading
import time
from logger import get_logger

logger = get_logger()

app = Flask(__name__)
CORS(app)

# Global bot instance (will be set from main.py)
bot_instance = None


def set_bot_instance(bot):
    """Set the bot instance for the web server"""
    global bot_instance
    bot_instance = bot


@app.route('/')
def index():
    """Serve the dashboard page"""
    return render_template('dashboard.html')


@app.route('/api/status')
def get_status():
    """Get current bot status"""
    if not bot_instance:
        return jsonify({"error": "Bot not initialized"}), 500
    
    try:
        from portfolio import portfolio
        from risk_manager import risk_manager

        # Get account balance - use cached balance (API fetch causes import errors)
        balance = portfolio.get_account_balance()

        # Get current position
        pos = portfolio.get_position("BTCUSDT")
        position_data = None
        if pos:
            position_data = {
                "symbol": pos.symbol,
                "direction": pos.direction,
                "entry_price": pos.entry_price,
                "size": pos.size,
                "unrealized_pnl": pos.current_pnl_net,
                "leverage": pos.leverage
            }

        # Get risk status
        risk_status = risk_manager.get_status(balance)

        # Check paused state
        is_paused = getattr(bot_instance, '_paused', False)

        return jsonify({
            "running": bot_instance._running,
            "paused": is_paused,
            "balance": balance,
            "daily_pnl": risk_status.daily_pnl,
            "daily_trades": risk_status.daily_trades,
            "consecutive_losses": risk_status.consecutive_losses,
            "position": position_data
        })
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/balance')
def get_balance():
    """Get account balance - use cached balance"""
    if not bot_instance:
        return jsonify({"error": "Bot not initialized"}), 500

    try:
        from portfolio import portfolio
        balance = portfolio.get_account_balance()
        return jsonify({"balance": balance})
    except Exception as e:
        logger.error(f"Balance endpoint error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/positions')
def get_positions():
    """Get current positions"""
    if not bot_instance:
        return jsonify({"error": "Bot not initialized"}), 500

    try:
        from portfolio import portfolio
        positions = portfolio.get_open_positions()
        positions_data = []
        for pos in positions:
            positions_data.append({
                "symbol": pos.symbol,
                "direction": pos.direction,
                "entry_price": pos.entry_price,
                "exit_price": pos.exit_price,
                "size": pos.size,
                "notional": pos.notional,
                "leverage": pos.leverage,
                "stop_loss": pos.stop_loss,
                "take_profit_1": pos.take_profit_1,
                "take_profit_2": pos.take_profit_2,
                "current_pnl_net": pos.current_pnl_net,
                "entry_reason": pos.entry_reason,
                "exit_reason": pos.exit_reason,
                "opened_at": pos.opened_at.isoformat() if pos.opened_at else None
            })
        return jsonify({"positions": positions_data})
    except Exception as e:
        import traceback
        logger.error(f"Error in /api/positions: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/api/positions/update_tp_sl', methods=['POST'])
def update_position_tp_sl():
    """Update TP/SL for an open position"""
    if not bot_instance:
        return jsonify({"error": "Bot not initialized"}), 500

    try:
        data = request.json
        symbol = data.get('symbol')
        stop_loss = data.get('stop_loss')
        take_profit = data.get('take_profit')

        if not symbol:
            return jsonify({"error": "Symbol is required"}), 400

        # Get current position info
        position_info = bot_instance.api.check_position_state(symbol)
        if not position_info:
            return jsonify({"error": f"No open position found for {symbol}"}), 404

        # Update portfolio position
        from portfolio import portfolio
        pos = portfolio.get_position(symbol)
        if pos:
            if stop_loss:
                pos.stop_loss = stop_loss
            if take_profit:
                pos.take_profit_1 = take_profit
                pos.take_profit_2 = take_profit * 1.5  # TP2 as 1.5x TP1

        logger.info(f"Updated TP/SL for {symbol}: SL={stop_loss}, TP={take_profit}")
        return jsonify({"status": "updated", "symbol": symbol, "stop_loss": stop_loss, "take_profit": take_profit})
    except Exception as e:
        logger.error(f"Error updating TP/SL: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/trade_history')
def get_trade_history():
    """Get trade history from portfolio and API"""
    if not bot_instance:
        return jsonify({"error": "Bot not initialized"}), 500

    try:
        from portfolio import portfolio

        # First, get portfolio history (locally tracked trades)
        portfolio_history = portfolio.get_trade_history()

        # Try to get additional trades from Bybit API
        try:
            api_history = bot_instance.api.get_order_history(limit=50)

            # Parse API response
            api_trades = []
            if api_history and isinstance(api_history, list):
                for trade in api_history:
                    if trade.get("orderStatus") == "Filled":
                        api_trades.append({
                            "id": trade.get("orderId", ""),
                            "symbol": trade.get("symbol", ""),
                            "direction": "long" if trade.get("side") == "Buy" else "short",
                            "entry": float(trade.get("avgPrice", 0)),
                            "exit": float(trade.get("avgPrice", 0)),
                            "pnl_net": 0,  # API doesn't provide PnL directly
                            "duration_min": 0,
                            "exit_reason": trade.get("orderStatus", "")
                        })

            # Combine portfolio and API history
            combined = portfolio_history + api_trades
            return jsonify({"history": combined, "source": "combined"})

        except Exception as api_error:
            logger.warning(f"Failed to fetch API history: {api_error}")
            # Return only portfolio history if API fails
            return jsonify({"history": portfolio_history, "source": "portfolio"})

    except Exception as e:
        logger.error(f"Trade history error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    """Start the bot"""
    if not bot_instance:
        return jsonify({"error": "Bot not initialized"}), 500
    
    try:
        if not bot_instance._running:
            bot_instance._running = True
            return jsonify({"status": "started"})
        return jsonify({"status": "already running"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    """Stop the bot"""
    if not bot_instance:
        return jsonify({"error": "Bot not initialized"}), 500

    try:
        if bot_instance._running:
            bot_instance._running = False
            return jsonify({"status": "stopped"})
        return jsonify({"status": "already stopped"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/bot/pause', methods=['POST'])
def pause_bot():
    """Pause/resume the bot"""
    if not bot_instance:
        return jsonify({"error": "Bot not initialized"}), 500

    try:
        if hasattr(bot_instance, '_paused'):
            bot_instance._paused = not bot_instance._paused
            status = "resumed" if not bot_instance._paused else "paused"
        else:
            bot_instance._paused = True
            status = "paused"
        return jsonify({"status": status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/logs')
def get_logs():
    """Get recent logs - filtered for important trade events"""
    try:
        # Read last 200 lines from log file
        log_file = "logs/bot.log"
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                recent_lines = lines[-200:] if len(lines) > 200 else lines

            # Filter for important trade events
            filtered_logs = []
            for line in recent_lines:
                # Keep only important events - expanded list for better visibility
                if any(keyword in line for keyword in [
                    'Позиция открыта',
                    'Позиция закрыта',
                    'Сигнал на вход',
                    'Сигнал на выход',
                    'Прибыль',
                    'Убыток',
                    'PnL',
                    'Стоп',
                    'Тейк',
                    'Entry failed',
                    'Exit failed',
                    'ERROR',
                    'WARNING',
                    'Бот на паузе',
                    'РАБОТАЕТ',
                    'ОСТАНОВЛЕН',
                    'Баланс',
                    'Открываю позицию',
                    'Закрываю позицию',
                    '📦',
                    '🚀',
                    '✅',
                    '❌',
                    '📊',
                    '🧠',
                    '🔄',
                    '⏸'
                ]):
                    # Clean up the log line - remove timestamp and level
                    parts = line.split('|')
                    if len(parts) >= 4:
                        # Keep only the message part
                        message = '|'.join(parts[3:]).strip()
                        filtered_logs.append(message)
                    else:
                        filtered_logs.append(line.strip())

            # If no important logs, show last 10 lines
            if not filtered_logs:
                filtered_logs = [line.strip() for line in recent_lines[-10:]]

            return jsonify({"logs": filtered_logs})
        except FileNotFoundError:
            return jsonify({"logs": ["No logs found"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/config')
def get_config():
    """Get current configuration - Smart Scalping"""
    try:
        from config import (
            trading_config, regime_config, strategy_config,
            risk_config, execution_config, fee_config
        )

        config_data = {
            "bot_name": trading_config.bot_name,
            "selected_template": trading_config.selected_template,
            "trading": {
                "symbol": trading_config.symbol,
                "symbols": trading_config.symbols,
                "main_timeframe": trading_config.main_timeframe,
                "context_timeframe": trading_config.context_timeframe,
                "max_positions": trading_config.max_positions,
                "max_daily_trades": trading_config.max_daily_trades,
                "max_leverage": trading_config.max_leverage,
                "default_leverage": trading_config.default_leverage,
                "min_leverage": trading_config.min_leverage,
                "symbol_max_leverage": trading_config.symbol_max_leverage,
                "category": trading_config.category,
                "default_demo_balance": trading_config.default_demo_balance,
                "balance_reset_increment": trading_config.balance_reset_increment
            },
            "regime": {
                "adx_trend_threshold": regime_config.adx_trend_threshold,
                "adx_chop_threshold": regime_config.adx_chop_threshold,
                "ema_fast": regime_config.ema_fast,
                "ema_medium": regime_config.ema_medium,
                "ema_slow": regime_config.ema_slow
            },
            "strategy": {
                "max_long_positions": strategy_config.max_long_positions,
                "max_short_positions": strategy_config.max_short_positions,
                "ema_fast_period": strategy_config.ema_fast_period,
                "ema_medium_period": strategy_config.ema_medium_period,
                "ema_slow_period": strategy_config.ema_slow_period,
                "rsi_period": strategy_config.rsi_period,
                "rsi_oversold": strategy_config.rsi_oversold,
                "rsi_overbought": strategy_config.rsi_overbought,
                "atr_period": strategy_config.atr_period,
                "min_atr_pct": strategy_config.min_atr_pct,
                "max_atr_pct": strategy_config.max_atr_pct,
                "tp_pct": strategy_config.tp_pct,
                "sl_pct": strategy_config.sl_pct,
                "tp_min_pct": strategy_config.tp_min_pct,
                "tp_max_pct": strategy_config.tp_max_pct,
                "sl_min_pct": strategy_config.sl_min_pct,
                "sl_max_pct": strategy_config.sl_max_pct,
                "partial_exit_pct": strategy_config.partial_exit_pct,
                "partial_exit_tp_pct": strategy_config.partial_exit_tp_pct,
                "min_price_change_pct": strategy_config.min_price_change_pct,
                "min_profit_multiple": strategy_config.min_profit_multiple,
                "vwap_period": strategy_config.vwap_period
            },
            "risk": {
                "risk_per_trade_pct": risk_config.risk_per_trade_pct,
                "max_risk_per_trade_pct": risk_config.max_risk_per_trade_pct,
                "max_daily_loss_pct": risk_config.max_daily_loss_pct,
                "max_consecutive_losses": risk_config.max_consecutive_losses,
                "atr_position_scaling": risk_config.atr_position_scaling,
                "min_position_size_usd": risk_config.min_position_size_usd,
                "max_position_size_usd": risk_config.max_position_size_usd,
                "max_position_pct_of_balance": risk_config.max_position_pct_of_balance,
                "auto_reverse_on_sl": risk_config.auto_reverse_on_sl,
                "auto_reopen_on_tp": risk_config.auto_reopen_on_tp
            },
            "execution": {
                "entry_order_type": execution_config.entry_order_type,
                "exit_order_type": execution_config.exit_order_type,
                "max_retries": execution_config.max_retries
            },
            "fees": {
                "maker_fee": fee_config.maker_fee,
                "taker_fee": fee_config.taker_fee,
                "round_trip_maker": fee_config.round_trip_maker,
                "round_trip_taker": fee_config.round_trip_taker
            }
        }
        return jsonify(config_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/config/update', methods=['POST'])
def update_config():
    """Update configuration - Smart Scalping"""
    try:
        data = request.json
        from config import (
            trading_config, regime_config, strategy_config,
            risk_config, execution_config, fee_config
        )

        # Pause bot if running
        was_running = False
        if bot_instance and bot_instance._running:
            bot_instance._paused = True
            was_running = True
            logger.info(" Bot paused for config update")

        # Update bot name
        if 'bot_name' in data:
            trading_config.bot_name = data['bot_name']

        # Update trading config
        if 'trading' in data:
            t = data['trading']
            if 'symbol' in t: trading_config.symbol = t['symbol']
            if 'symbols' in t: trading_config.symbols = t['symbols']
            if 'main_timeframe' in t: trading_config.main_timeframe = t['main_timeframe']
            if 'context_timeframe' in t: trading_config.context_timeframe = t['context_timeframe']
            if 'max_positions' in t: trading_config.max_positions = int(t['max_positions'])
            if 'max_daily_trades' in t: trading_config.max_daily_trades = int(t['max_daily_trades'])
            if 'max_leverage' in t: trading_config.max_leverage = int(t['max_leverage'])
            if 'default_leverage' in t: trading_config.default_leverage = int(t['default_leverage'])
            if 'min_leverage' in t: trading_config.min_leverage = int(t['min_leverage'])
            if 'leverage_scaling' in t: trading_config.leverage_scaling = t['leverage_scaling']
            if 'symbol_max_leverage' in t: trading_config.symbol_max_leverage = t['symbol_max_leverage']
            if 'default_demo_balance' in t: trading_config.default_demo_balance = float(t['default_demo_balance'])
            if 'balance_reset_increment' in t: trading_config.balance_reset_increment = float(t['balance_reset_increment'])

        # Update regime config
        if 'regime' in data:
            r = data['regime']
            if 'adx_trend_threshold' in r: regime_config.adx_trend_threshold = float(r['adx_trend_threshold'])
            if 'adx_chop_threshold' in r: regime_config.adx_chop_threshold = float(r['adx_chop_threshold'])
            if 'ema_fast' in r: regime_config.ema_fast = int(r['ema_fast'])
            if 'ema_medium' in r: regime_config.ema_medium = int(r['ema_medium'])
            if 'ema_slow' in r: regime_config.ema_slow = int(r['ema_slow'])

        # Update strategy config
        if 'strategy' in data:
            s = data['strategy']
            if 'max_long_positions' in s: strategy_config.max_long_positions = int(s['max_long_positions'])
            if 'max_short_positions' in s: strategy_config.max_short_positions = int(s['max_short_positions'])
            if 'ema_fast_period' in s: strategy_config.ema_fast_period = int(s['ema_fast_period'])
            if 'ema_medium_period' in s: strategy_config.ema_medium_period = int(s['ema_medium_period'])
            if 'ema_slow_period' in s: strategy_config.ema_slow_period = int(s['ema_slow_period'])
            if 'rsi_period' in s: strategy_config.rsi_period = int(s['rsi_period'])
            if 'rsi_oversold' in s: strategy_config.rsi_oversold = int(s['rsi_oversold'])
            if 'rsi_overbought' in s: strategy_config.rsi_overbought = int(s['rsi_overbought'])
            if 'rsi_long_min' in s: strategy_config.rsi_oversold = int(s['rsi_long_min'])
            if 'rsi_long_max' in s: strategy_config.rsi_overbought = int(s['rsi_long_max'])
            if 'rsi_short_min' in s: strategy_config.rsi_oversold = int(s['rsi_short_min'])
            if 'rsi_short_max' in s: strategy_config.rsi_overbought = int(s['rsi_short_max'])
            if 'sl_min_pct' in s: strategy_config.sl_min_pct = float(s['sl_min_pct'])
            if 'tp_min_pct' in s: strategy_config.tp_min_pct = float(s['tp_min_pct'])
            if 'tp_max_pct' in s: strategy_config.tp_max_pct = float(s['tp_max_pct'])
            if 'min_atr_pct' in s: strategy_config.min_atr_pct = float(s['min_atr_pct'])
            if 'max_atr_pct' in s: strategy_config.max_atr_pct = float(s['max_atr_pct'])
            if 'vwap_period' in s: strategy_config.vwap_period = int(s['vwap_period'])
            # Use tp_roi_pct/sl_roi_pct from web console and map to tp_pct/sl_pct
            if 'tp_roi_pct' in s: strategy_config.tp_pct = float(s['tp_roi_pct'])
            if 'sl_roi_pct' in s: strategy_config.sl_pct = float(s['sl_roi_pct'])
            # Also update the legacy fields for compatibility
            if 'tp_roi_pct' in s: strategy_config.tp_roi_pct = float(s['tp_roi_pct'])
            if 'sl_roi_pct' in s: strategy_config.sl_roi_pct = float(s['sl_roi_pct'])

        # Update risk config
        if 'risk' in data:
            r = data['risk']
            if 'risk_per_trade_pct' in r: risk_config.risk_per_trade_pct = float(r['risk_per_trade_pct'])
            if 'max_risk_per_trade_pct' in r: risk_config.max_risk_per_trade_pct = float(r['max_risk_per_trade_pct'])
            if 'max_daily_loss_pct' in r: risk_config.max_daily_loss_pct = float(r['max_daily_loss_pct'])
            if 'max_consecutive_losses' in r: risk_config.max_consecutive_losses = int(r['max_consecutive_losses'])
            if 'atr_position_scaling' in r: risk_config.atr_position_scaling = r['atr_position_scaling']
            if 'min_position_size_usd' in r: risk_config.min_position_size_usd = float(r['min_position_size_usd'])
            if 'max_position_size_usd' in r: risk_config.max_position_size_usd = float(r['max_position_size_usd'])
            if 'max_position_pct_of_balance' in r: risk_config.max_position_pct_of_balance = float(r['max_position_pct_of_balance'])
            if 'auto_reverse_on_sl' in r: risk_config.auto_reverse_on_sl = r['auto_reverse_on_sl']
            if 'auto_reopen_on_tp' in r: risk_config.auto_reopen_on_tp = r['auto_reopen_on_tp']

        # Update execution config
        if 'execution' in data:
            e = data['execution']
            if 'entry_order_type' in e: execution_config.entry_order_type = e['entry_order_type']
            if 'exit_order_type' in e: execution_config.exit_order_type = e['exit_order_type']
            if 'max_retries' in e: execution_config.max_retries = int(e['max_retries'])

        # Update fee config
        if 'fee' in data:
            f = data['fee']
            if 'maker_fee' in f: fee_config.maker_fee = float(f['maker_fee'])
            if 'taker_fee' in f: fee_config.taker_fee = float(f['taker_fee'])

        logger.info(f" Configuration updated")
        logger.info(f"   min_atr_pct: {strategy_config.min_atr_pct}")
        logger.info(f"   max_atr_pct: {strategy_config.max_atr_pct}")
        logger.info(f"   rsi_oversold: {strategy_config.rsi_oversold}")
        logger.info(f"   rsi_overbought: {strategy_config.rsi_overbought}")

        # Resume bot if it was running
        if bot_instance and bot_instance._paused:
            bot_instance._paused = False
            logger.info(" Bot resumed with new config")

        return jsonify({"status": "updated", "paused_and_resumed": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/account/reset_balance', methods=['POST'])
def reset_balance():
    """Reset demo account balance to default"""
    if not bot_instance:
        return jsonify({"error": "Bot not initialized"}), 500

    try:
        from config import trading_config
        from portfolio import portfolio

        # Get current balance
        current_balance = portfolio.get_account_balance()

        # Calculate how much to add to reach default
        target_balance = trading_config.default_demo_balance
        increment = trading_config.balance_reset_increment

        if current_balance >= target_balance:
            return jsonify({"status": "already_at_target", "balance": current_balance})

        # Calculate number of increments needed
        needed = target_balance - current_balance
        num_increments = int((needed + increment - 1) // increment)  # Round up

        # For demo accounts, we can only simulate the reset
        # Bybit testnet doesn't have an API to directly reset balance
        # The actual Bybit demo account balance cannot be reset via API
        # We'll log it and update the portfolio cache for simulation purposes
        logger.info(f"🔄 Simulating balance reset: ${current_balance:.2f} → ${target_balance:.2f}")
        logger.info(f"   Increments needed: {num_increments} x ${increment:.2f}")
        logger.warning(f"   ВНИМАНИЕ: Bybit Demo Account НЕ поддерживает сброс баланса через API")
        logger.warning(f"   Это только симуляция в портфеле бота. Для реального сброса используйте веб-интерфейс Bybit.")

        # Update portfolio balance (simulated)
        portfolio._balance = target_balance

        return jsonify({
            "status": "reset",
            "previous_balance": current_balance,
            "new_balance": target_balance,
            "increments_applied": num_increments,
            "increment_size": increment
        })
    except Exception as e:
        logger.error(f"Balance reset error: {e}")
        return jsonify({"error": str(e)}), 500


def run_web_server(host='127.0.0.1', port=5000):
    """Run the Flask web server"""
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    # For standalone testing
    print("Starting web server on http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=False)
