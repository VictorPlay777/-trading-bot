"""
Web Dashboard for Adaptive Momentum Trading Bot
Flask-based real-time statistics and monitoring
"""
from flask import Flask, jsonify, render_template_string
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global reference to trading engine (set by engine)
trading_engine = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Trading Bot Dashboard</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #1a1a1a;
            color: #fff;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            color: #00ff88;
            text-align: center;
            margin-bottom: 30px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #2a2a2a;
            padding: 20px;
            border-radius: 10px;
            border-left: 4px solid #00ff88;
        }
        .stat-card.error {
            border-left-color: #ff4444;
        }
        .stat-card.warning {
            border-left-color: #ffaa00;
        }
        .stat-label {
            color: #888;
            font-size: 12px;
            text-transform: uppercase;
        }
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            margin: 10px 0;
        }
        .positive {
            color: #00ff88;
        }
        .negative {
            color: #ff4444;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: #2a2a2a;
            border-radius: 10px;
            overflow: hidden;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #444;
        }
        th {
            background: #333;
            color: #00ff88;
            font-weight: bold;
        }
        tr:hover {
            background: #333;
        }
        .badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }
        .badge-long {
            background: #00ff88;
            color: #000;
        }
        .badge-short {
            background: #ff4444;
            color: #fff;
        }
        .badge-probe {
            background: #ffaa00;
            color: #000;
        }
        .badge-scout {
            background: #00aaff;
            color: #fff;
        }
        .badge-momentum {
            background: #ff00ff;
            color: #fff;
        }
        .section {
            margin-bottom: 30px;
        }
        .section-title {
            color: #00ff88;
            font-size: 18px;
            margin-bottom: 15px;
            border-bottom: 2px solid #333;
            padding-bottom: 10px;
        }
        .timestamp {
            text-align: center;
            color: #666;
            font-size: 12px;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Adaptive Momentum Trading Bot</h1>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Active Positions</div>
                <div class="stat-value">{{ stats.active_positions }} / {{ stats.total_symbols }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total PnL</div>
                <div class="stat-value {{ 'positive' if stats.total_pnl > 0 else 'negative' }}">${{ "%.2f"|format(stats.total_pnl) }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Win Rate</div>
                <div class="stat-value">{{ "%.1f"|format(stats.win_rate * 100) }}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Trades</div>
                <div class="stat-value">{{ stats.total_trades }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Account Balance</div>
                <div class="stat-value">${{ "%.2f"|format(stats.balance) }}</div>
            </div>
            <div class="stat-card {{ 'error' if stats.uptime < 60 else '' }}">
                <div class="stat-label">Uptime</div>
                <div class="stat-value">{{ stats.uptime }}s</div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">📊 Active Positions</div>
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Direction</th>
                        <th>Type</th>
                        <th>Entry Price</th>
                        <th>Quantity</th>
                        <th>PnL</th>
                        <th>Leverage</th>
                    </tr>
                </thead>
                <tbody>
                    {% for pos in positions %}
                    <tr>
                        <td><strong>{{ pos.symbol }}</strong></td>
                        <td><span class="badge badge-{{ pos.direction }}">{{ pos.direction.upper() }}</span></td>
                        <td><span class="badge badge-{{ pos.trade_type }}">{{ pos.trade_type.upper() }}</span></td>
                        <td>${{ "%.2f"|format(pos.entry_price) }}</td>
                        <td>{{ "%.4f"|format(pos.quantity) }}</td>
                        <td class="{{ 'positive' if pos.pnl > 0 else 'negative' }}">${{ "%.2f"|format(pos.pnl) }}</td>
                        <td>{{ pos.leverage }}x</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <div class="section-title">📈 Top Performing Symbols</div>
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Trades</th>
                        <th>Win Rate</th>
                        <th>Avg PnL</th>
                        <th>Total PnL</th>
                    </tr>
                </thead>
                <tbody>
                    {% for symbol, sym_stats in symbol_stats %}
                    <tr>
                        <td><strong>{{ symbol }}</strong></td>
                        <td>{{ sym_stats.trades }}</td>
                        <td class="{{ 'positive' if sym_stats.winrate > 0.5 else 'negative' }}">{{ "%.1f"|format(sym_stats.winrate * 100) }}%</td>
                        <td class="{{ 'positive' if sym_stats.avg_pnl > 0 else 'negative' }}">${{ "%.2f"|format(sym_stats.avg_pnl) }}</td>
                        <td class="{{ 'positive' if sym_stats.total_pnl > 0 else 'negative' }}">${{ "%.2f"|format(sym_stats.total_pnl) }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="timestamp">Last updated: {{ timestamp }} | Auto-refresh every 5 seconds</div>
    </div>
</body>
</html>
"""


@app.route('/')
def dashboard():
    """Main dashboard page"""
    try:
        if not trading_engine:
            return "Trading engine not initialized", 503
        
        # Get current stats
        stats = get_dashboard_stats()
        positions = get_positions_data()
        symbol_stats = get_symbol_stats()
        
        return render_template_string(
            HTML_TEMPLATE,
            stats=stats,
            positions=positions,
            symbol_stats=symbol_stats,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
    except Exception as e:
        logger.error(f"Error rendering dashboard: {e}")
        return f"Error: {str(e)}", 500


@app.route('/api/stats')
def api_stats():
    """API endpoint for stats"""
    return jsonify(get_dashboard_stats())


@app.route('/api/positions')
def api_positions():
    """API endpoint for positions"""
    return jsonify(get_positions_data())


@app.route('/api/symbol-stats')
def api_symbol_stats():
    """API endpoint for symbol statistics"""
    return jsonify(get_symbol_stats())


def get_dashboard_stats() -> Dict:
    """Get dashboard statistics"""
    try:
        if not trading_engine:
            return {
                'active_positions': 0,
                'total_symbols': 0,
                'total_pnl': 0,
                'win_rate': 0,
                'total_trades': 0,
                'balance': 0,
                'uptime': 0
            }
        
        positions = trading_engine.position_manager.get_all_positions()
        symbol_stats = trading_engine.symbol_stats
        
        # Calculate total PnL (realized from closed + unrealized from open)
        realized_pnl = sum(s.total_pnl for s in symbol_stats.values())
        unrealized_pnl = sum(p.pnl for p in positions)
        total_pnl = realized_pnl + unrealized_pnl
        
        # Calculate win rate
        total_trades = sum(s.trades for s in symbol_stats.values())
        winning_trades = sum(s.wins for s in symbol_stats.values())
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Get balance
        try:
            balance = trading_engine._get_account_balance()
        except:
            balance = 100000.0
        
        return {
            'active_positions': len(positions),
            'total_symbols': len(trading_engine.symbols),
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'balance': balance,
            'uptime': getattr(trading_engine, 'uptime_seconds', 0)
        }
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        return {
            'active_positions': 0,
            'total_symbols': 0,
            'total_pnl': 0,
            'win_rate': 0,
            'total_trades': 0,
            'balance': 0,
            'uptime': 0,
            'error': str(e)
        }


def get_positions_data() -> List[Dict]:
    """Get formatted positions data"""
    try:
        if not trading_engine:
            return []
        
        positions = trading_engine.position_manager.get_all_positions()
        return [
            {
                'symbol': p.symbol,
                'direction': p.direction,
                'trade_type': p.trade_type.value,
                'entry_price': p.entry_price,
                'quantity': p.quantity,
                'pnl': p.pnl,
                'leverage': p.leverage,
                'stop_loss': p.stop_loss,
                'take_profit': p.take_profit
            }
            for p in positions
        ]
    except Exception as e:
        logger.error(f"Error getting positions data: {e}")
        return []


def get_symbol_stats() -> List[tuple]:
    """Get sorted symbol statistics"""
    try:
        if not trading_engine:
            return []
        
        stats = trading_engine.symbol_stats
        sorted_stats = sorted(
            stats.items(),
            key=lambda x: x[1].winrate,
            reverse=True
        )
        return sorted_stats[:20]  # Top 20
    except Exception as e:
        logger.error(f"Error getting symbol stats: {e}")
        return []


def start_dashboard(engine, host='0.0.0.0', port=5000):
    """Start the web dashboard in a separate thread"""
    global trading_engine
    trading_engine = engine
    
    def run_flask():
        try:
            logger.info(f"Starting web dashboard on http://{host}:{port}")
            app.run(host=host, port=port, debug=False, threaded=True)
        except Exception as e:
            logger.error(f"Error starting dashboard: {e}")
    
    # Start Flask in a daemon thread
    dashboard_thread = threading.Thread(target=run_flask, daemon=True)
    dashboard_thread.start()
    logger.info(f"Dashboard thread started on port {port}")


if __name__ == '__main__':
    # For testing only
    app.run(host='0.0.0.0', port=5000, debug=True)
