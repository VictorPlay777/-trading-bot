"""
Multi-Bot Dashboard - Web interface for managing multiple trading bots
Features: Start/Stop/Pause bots, compare performance, edit configs live
"""
from flask import Flask, jsonify, render_template_string, request
import logging
from typing import Dict, List
from datetime import datetime

from bot_manager import get_manager, BotManager

app = Flask(__name__)
logger = logging.getLogger(__name__)

# HTML Template with modern UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Multi-Bot Trading Manager</title>
    <meta http-equiv="refresh" content="10">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            min-height: 100vh;
        }
        .header {
            background: rgba(0,0,0,0.3);
            padding: 20px;
            border-bottom: 2px solid #00ff88;
        }
        .header h1 { color: #00ff88; font-size: 28px; }
        .header .subtitle { color: #888; font-size: 14px; margin-top: 5px; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        
        /* Stats Overview */
        .overview {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.05);
            padding: 20px;
            border-radius: 12px;
            border-left: 4px solid #00ff88;
        }
        .stat-card.error { border-left-color: #ff4444; }
        .stat-card.warning { border-left-color: #ffaa00; }
        .stat-label { color: #888; font-size: 12px; text-transform: uppercase; }
        .stat-value { font-size: 24px; font-weight: bold; margin-top: 8px; }
        .positive { color: #00ff88; }
        .negative { color: #ff4444; }
        
        /* Bot Cards */
        .bots-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .bot-card {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.1);
            transition: all 0.3s;
        }
        .bot-card:hover { border-color: #00ff88; }
        .bot-card.running { border-left: 4px solid #00ff88; }
        .bot-card.stopped { border-left: 4px solid #ff4444; }
        .bot-card.paused { border-left: 4px solid #ffaa00; }
        
        .bot-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .bot-name { font-size: 18px; font-weight: bold; }
        .bot-id { color: #888; font-size: 12px; }
        .status-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }
        .status-running { background: #00ff88; color: #000; }
        .status-stopped { background: #ff4444; color: #fff; }
        .status-paused { background: #ffaa00; color: #000; }
        .status-starting { background: #00aaff; color: #fff; }
        
        .bot-stats {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin: 15px 0;
        }
        .bot-stat {
            background: rgba(0,0,0,0.2);
            padding: 10px;
            border-radius: 8px;
        }
        .bot-stat-label { color: #888; font-size: 11px; }
        .bot-stat-value { font-size: 16px; font-weight: bold; margin-top: 4px; }
        
        .bot-actions {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        .btn {
            flex: 1;
            padding: 10px 15px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.2s;
        }
        .btn:hover { transform: translateY(-2px); }
        .btn-start { background: #00ff88; color: #000; }
        .btn-stop { background: #ff4444; color: #fff; }
        .btn-pause { background: #ffaa00; color: #000; }
        .btn-edit { background: #00aaff; color: #fff; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        
        /* Leaderboard */
        .leaderboard {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            margin-top: 30px;
        }
        .section-title {
            color: #00ff88;
            font-size: 20px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th {
            color: #888;
            font-weight: normal;
            text-transform: uppercase;
            font-size: 12px;
        }
        .rank {
            font-size: 24px;
            font-weight: bold;
            color: #00ff88;
        }
        .rank-1 { color: #ffd700; } /* Gold */
        .rank-2 { color: #c0c0c0; } /* Silver */
        .rank-3 { color: #cd7f32; } /* Bronze */
        
        /* Create Bot Form */
        .create-form {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            margin-top: 30px;
        }
        .form-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
        }
        .form-group {
            display: flex;
            flex-direction: column;
        }
        .form-group label {
            color: #888;
            font-size: 12px;
            margin-bottom: 5px;
        }
        .form-group input, .form-group select {
            padding: 10px;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            background: rgba(0,0,0,0.3);
            color: #fff;
            font-size: 14px;
        }
        .form-group input:focus, .form-group select:focus {
            outline: none;
            border-color: #00ff88;
        }
        
        .footer {
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 12px;
        }
        
        @media (max-width: 768px) {
            .bots-grid { grid-template-columns: 1fr; }
            .bot-actions { flex-wrap: wrap; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 Multi-Bot Trading Manager</h1>
        <div class="subtitle">Manage multiple trading strategies from one dashboard</div>
    </div>
    
    <div class="container">
        <!-- Overview Stats -->
        <div class="overview">
            <div class="stat-card">
                <div class="stat-label">Total Bots</div>
                <div class="stat-value">{{ overview.total_bots }}</div>
            </div>
            <div class="stat-card {% if overview.running_bots > 0 %}positive{% endif %}">
                <div class="stat-label">Running</div>
                <div class="stat-value">{{ overview.running_bots }}</div>
            </div>
            <div class="stat-card {% if overview.stopped_bots > 0 %}error{% endif %}">
                <div class="stat-label">Stopped</div>
                <div class="stat-value">{{ overview.stopped_bots }}</div>
            </div>
            <div class="stat-card {% if overview.aggregate_pnl > 0 %}positive{% else %}negative{% endif %}">
                <div class="stat-label">Total PnL</div>
                <div class="stat-value">${{ "%.2f"|format(overview.aggregate_pnl) }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Trades</div>
                <div class="stat-value">{{ overview.aggregate_trades }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Active Positions</div>
                <div class="stat-value">{{ overview.aggregate_positions }}</div>
            </div>
        </div>
        
        <!-- Bot Cards -->
        <div class="bots-grid">
            {% for bot in bots %}
            <div class="bot-card {{ bot.status }}">
                <div class="bot-header">
                    <div>
                        <div class="bot-name">{{ bot.name }}</div>
                        <div class="bot-id">{{ bot.bot_id }}</div>
                    </div>
                    <span class="status-badge status-{{ bot.status }}">{{ bot.status }}</span>
                </div>
                
                <div class="bot-stats">
                    <div class="bot-stat">
                        <div class="bot-stat-label">Win Rate</div>
                        <div class="bot-stat-value {% if bot.stats.win_rate > 0.5 %}positive{% endif %}">
                            {{ "%.1f"|format(bot.stats.win_rate * 100) }}%
                        </div>
                    </div>
                    <div class="bot-stat">
                        <div class="bot-stat-label">Total PnL</div>
                        <div class="bot-stat-value {% if bot.stats.total_pnl > 0 %}positive{% else %}negative{% endif %}">
                            ${{ "%.2f"|format(bot.stats.total_pnl) }}
                        </div>
                    </div>
                    <div class="bot-stat">
                        <div class="bot-stat-label">Trades</div>
                        <div class="bot-stat-value">{{ bot.stats.total_trades }}</div>
                    </div>
                    <div class="bot-stat">
                        <div class="bot-stat-label">Positions</div>
                        <div class="bot-stat-value">{{ bot.stats.active_positions }} / {{ bot.stats.max_positions }}</div>
                    </div>
                </div>
                
                <div class="bot-actions">
                    {% if bot.status == 'stopped' or bot.status == 'error' %}
                    <button class="btn btn-start" onclick="startBot('{{ bot.bot_id }}')">▶ Start</button>
                    {% else %}
                    <button class="btn btn-stop" onclick="stopBot('{{ bot.bot_id }}')">⏹ Stop</button>
                    {% endif %}
                    
                    {% if bot.status == 'running' %}
                    <button class="btn btn-pause" onclick="pauseBot('{{ bot.bot_id }}')">⏸ Pause</button>
                    {% endif %}
                    
                    <button class="btn btn-edit" onclick="editBot('{{ bot.bot_id }}')">⚙ Edit</button>
                </div>
            </div>
            {% endfor %}
        </div>
        
        <!-- Leaderboard -->
        <div class="leaderboard">
            <div class="section-title">🏆 Performance Leaderboard</div>
            <table>
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Bot</th>
                        <th>Status</th>
                        <th>Win Rate</th>
                        <th>Total PnL</th>
                        <th>Trades</th>
                        <th>Active</th>
                        <th>Score</th>
                    </tr>
                </thead>
                <tbody>
                    {% for bot in leaderboard %}
                    <tr>
                        <td class="rank rank-{{ bot.rank }}">#{{ bot.rank }}</td>
                        <td>
                            <strong>{{ bot.name }}</strong><br>
                            <small style="color:#888">{{ bot.bot_id }}</small>
                        </td>
                        <td><span class="status-badge status-{{ bot.status }}">{{ bot.status }}</span></td>
                        <td>{{ bot.win_rate }}</td>
                        <td class="{% if bot.total_pnl.startswith('$-') %}negative{% else %}positive{% endif %}">{{ bot.total_pnl }}</td>
                        <td>{{ bot.total_trades }}</td>
                        <td>{{ bot.active_positions }}</td>
                        <td><strong>{{ bot.score }}</strong></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <!-- Create New Bot -->
        <div class="create-form">
            <div class="section-title">➕ Create New Bot</div>
            <form id="createBotForm">
                <div class="form-row">
                    <div class="form-group">
                        <label>Name</label>
                        <input type="text" id="botName" placeholder="My Strategy" required>
                    </div>
                    <div class="form-group">
                        <label>Type</label>
                        <select id="botType">
                            <option value="aggressive">Aggressive (100x)</option>
                            <option value="conservative">Conservative (10x)</option>
                            <option value="alts">Alts Specialist (50x)</option>
                            <option value="custom">Custom</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>API Key Env</label>
                        <input type="text" id="apiKeyEnv" placeholder="BYBIT_API_KEY_1" required>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Max Positions</label>
                        <input type="number" id="maxPositions" value="20" min="1" max="100">
                    </div>
                    <div class="form-group">
                        <label>Leverage</label>
                        <input type="number" id="leverage" value="10" min="1" max="100">
                    </div>
                    <div class="form-group">
                        <label>Testnet</label>
                        <select id="testnet">
                            <option value="true">Yes (Safe)</option>
                            <option value="false">No (Real Money)</option>
                        </select>
                    </div>
                </div>
                <button type="submit" class="btn btn-start" style="width:100%">Create Bot</button>
            </form>
        </div>
        
        <div class="footer">
            Auto-refresh every 10 seconds | Last updated: {{ timestamp }}
        </div>
    </div>
    
    <script>
        function startBot(botId) {
            fetch(`/api/bots/${botId}/start`, {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    alert(data.message || 'Bot started');
                    location.reload();
                });
        }
        
        function stopBot(botId) {
            if (!confirm('Stop bot ' + botId + '?')) return;
            fetch(`/api/bots/${botId}/stop`, {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    alert(data.message || 'Bot stopped');
                    location.reload();
                });
        }
        
        function pauseBot(botId) {
            fetch(`/api/bots/${botId}/pause`, {method: 'POST'})
                .then(r => r.json())
                .then(data => location.reload());
        }
        
        function editBot(botId) {
            window.location.href = `/bots/${botId}/edit`;
        }
        
        document.getElementById('createBotForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const data = {
                name: document.getElementById('botName').value,
                type: document.getElementById('botType').value,
                api_key_env: document.getElementById('apiKeyEnv').value,
                max_positions: parseInt(document.getElementById('maxPositions').value),
                leverage: parseInt(document.getElementById('leverage').value),
                testnet: document.getElementById('testnet').value === 'true'
            };
            
            fetch('/api/bots', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(data => {
                alert('Bot created: ' + data.bot_id);
                location.reload();
            });
        });
    </script>
</body>
</html>
"""


# Initialize manager
manager = get_manager()


@app.route('/')
def dashboard():
    """Main dashboard"""
    try:
        overview = manager.get_aggregate_stats()
        bots = manager.get_all_status()
        leaderboard = manager.get_leaderboard()
        
        return render_template_string(
            HTML_TEMPLATE,
            overview=overview,
            bots=bots,
            leaderboard=leaderboard,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return f"Error: {str(e)}", 500


@app.route('/api/bots', methods=['GET'])
def get_bots():
    """Get all bots status"""
    return jsonify(manager.get_all_status())


@app.route('/api/bots', methods=['POST'])
def create_bot():
    """Create new bot"""
    try:
        data = request.json
        
        # Build config from template
        templates = {
            'aggressive': 'bot_configs/bot_1_aggressive.json',
            'conservative': 'bot_configs/bot_2_conservative.json',
            'alts': 'bot_configs/bot_3_alts_only.json'
        }
        
        if data.get('type') in templates:
            import json
            with open(templates[data['type']], 'r') as f:
                config = json.load(f)
        else:
            config = {}
        
        # Override with user settings
        config['name'] = data.get('name', 'New Bot')
        config['api']['key_env'] = data.get('api_key_env', 'BYBIT_API_KEY')
        config['api']['secret_env'] = data.get('api_key_env', 'BYBIT_API_KEY').replace('KEY', 'SECRET')
        config['api']['testnet'] = data.get('testnet', True)
        config['strategy']['max_positions'] = data.get('max_positions', 20)
        config['strategy']['leverage'] = data.get('leverage', 10)
        config['enabled'] = False  # Don't auto-start
        
        bot_id = manager.create_bot(config)
        
        if bot_id:
            return jsonify({'success': True, 'bot_id': bot_id, 'message': 'Bot created'})
        else:
            return jsonify({'success': False, 'error': 'Failed to create bot'}), 400
            
    except Exception as e:
        logger.error(f"Create bot error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bots/<bot_id>/start', methods=['POST'])
def start_bot(bot_id):
    """Start a bot"""
    success = manager.start_bot(bot_id)
    return jsonify({
        'success': success,
        'bot_id': bot_id,
        'status': 'running' if success else 'error',
        'message': 'Bot started' if success else 'Failed to start'
    })


@app.route('/api/bots/<bot_id>/stop', methods=['POST'])
def stop_bot(bot_id):
    """Stop a bot"""
    success = manager.stop_bot(bot_id)
    return jsonify({
        'success': success,
        'bot_id': bot_id,
        'status': 'stopped' if success else 'error',
        'message': 'Bot stopped' if success else 'Failed to stop'
    })


@app.route('/api/bots/<bot_id>/pause', methods=['POST'])
def pause_bot(bot_id):
    """Pause a bot"""
    success = manager.pause_bot(bot_id)
    return jsonify({
        'success': success,
        'bot_id': bot_id,
        'status': 'paused' if success else 'error'
    })


@app.route('/api/bots/<bot_id>/resume', methods=['POST'])
def resume_bot(bot_id):
    """Resume a paused bot"""
    success = manager.resume_bot(bot_id)
    return jsonify({
        'success': success,
        'bot_id': bot_id,
        'status': 'running' if success else 'error'
    })


@app.route('/api/bots/<bot_id>', methods=['GET'])
def get_bot(bot_id):
    """Get detailed bot info"""
    status = manager.get_bot_status(bot_id)
    if status:
        return jsonify(status)
    return jsonify({'error': 'Bot not found'}), 404


@app.route('/api/bots/<bot_id>', methods=['PUT'])
def update_bot(bot_id):
    """Update bot configuration"""
    try:
        updates = request.json
        success = manager.update_bot_config(bot_id, updates)
        return jsonify({
            'success': success,
            'bot_id': bot_id,
            'message': 'Config updated' if success else 'Failed to update'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bots/<bot_id>/logs', methods=['GET'])
def get_bot_logs(bot_id):
    """Get bot logs"""
    lines = request.args.get('lines', 100, type=int)
    logs = manager.get_bot_logs(bot_id, lines)
    return jsonify({'bot_id': bot_id, 'logs': logs})


@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    """Get performance leaderboard"""
    return jsonify(manager.get_leaderboard())


@app.route('/api/overview', methods=['GET'])
def get_overview():
    """Get aggregate overview"""
    return jsonify(manager.get_aggregate_stats())


@app.route('/bots/<bot_id>/edit')
def edit_bot_page(bot_id):
    """Bot edit page"""
    # TODO: Create detailed edit page
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Edit {bot_id}</title></head>
    <body>
        <h1>Edit Bot: {bot_id}</h1>
        <p>Edit configuration here (TODO)</p>
        <a href="/">Back to Dashboard</a>
    </body>
    </html>
    """


def start_dashboard(host='0.0.0.0', port=5001):
    """Start the multi-bot dashboard"""
    logger.info(f"Starting Multi-Bot Dashboard on http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    start_dashboard()
