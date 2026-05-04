"""
Multi-Bot Dashboard - Web interface for managing multiple trading bots
Features: Start/Stop/Pause bots, compare performance, edit configs live
"""
from flask import Flask, jsonify, render_template_string, request
import logging
from typing import Dict, List
from datetime import datetime
import os
try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None

from bot_manager import get_manager, BotManager

app = Flask(__name__)
logger = logging.getLogger(__name__)

# HTML Template with modern UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Multi-Bot Trading Manager</title>
    <!-- No auto-refresh meta - it breaks JS fetch calls -->
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
        .btn-logs { background: #9b59b6; color: #fff; }
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
            <div class="bot-card {{ bot.status }}" data-bot-id="{{ bot.bot_id }}">
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
                    <button class="btn btn-logs" onclick="showLogs('{{ bot.bot_id }}')">📋 Логи</button>
                </div>
            </div>
            {% endfor %}
        </div>
        
        <!-- Logs Modal -->
        <div id="logsModal" class="modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); z-index:1000;">
            <div style="background:#1a1a2e; margin:50px auto; padding:20px; width:80%; max-height:80%; overflow:auto; border-radius:12px; border:2px solid #00ff88;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                    <h2 style="color:#00ff88; margin:0;">📋 Логи: <span id="logsBotName"></span></h2>
                    <button onclick="closeLogs()" style="background:#ff4444; color:white; border:none; padding:10px 20px; border-radius:8px; cursor:pointer;">❌ Закрыть</button>
                </div>
                <pre id="logsContent" style="background:#0a0a0a; color:#00ff88; padding:15px; border-radius:8px; max-height:500px; overflow:auto; font-family:monospace; font-size:12px;"></pre>
                <div style="margin-top:10px;">
                    <button onclick="refreshLogs()" style="background:#00ff88; color:#000; border:none; padding:10px 20px; border-radius:8px; cursor:pointer; font-weight:bold;">🔄 Обновить</button>
                    <button onclick="clearLogs()" style="background:#ffaa00; color:#000; border:none; padding:10px 20px; border-radius:8px; cursor:pointer; font-weight:bold; margin-left:10px;">🗑️ Очистить</button>
                </div>
            </div>
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
            var badge = document.querySelector('[data-bot-id="' + botId + '"] .status-badge');
            if (badge) { badge.textContent = 'starting...'; badge.className = 'status-badge status-starting'; }
            var btn = event.target; btn.disabled = true; btn.textContent = '⏳ Starting...';
            fetch('/api/bots/' + botId + '/start', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    if (!data.success) {
                        alert('❌ ' + data.message);
                        btn.disabled = false; btn.textContent = '▶ Start';
                        if (badge) { badge.textContent = 'stopped'; badge.className = 'status-badge status-stopped'; }
                        return;
                    }
                    // Poll status until running or error
                    var checks = 0;
                    var pollId = setInterval(function() {
                        fetch('/api/bots/' + botId)
                            .then(r => r.json())
                            .then(bot => {
                                if (bot.status === 'running') {
                                    clearInterval(pollId);
                                    if (badge) { badge.textContent = 'running'; badge.className = 'status-badge status-running'; }
                                    btn.textContent = '⏹ Stop'; btn.className = 'btn btn-stop'; btn.disabled = false;
                                    btn.setAttribute('onclick', "stopBot('" + botId + "')");
                                    alert('✅ Bot ' + botId + ' запущен!');
                                } else if (bot.status === 'error' || bot.status === 'stopped') {
                                    clearInterval(pollId);
                                    if (badge) { badge.textContent = bot.status; badge.className = 'status-badge status-stopped'; }
                                    btn.disabled = false; btn.textContent = '▶ Start';
                                    alert('❌ Bot failed to start');
                                }
                                checks++;
                                if (checks > 30) { clearInterval(pollId); btn.disabled = false; btn.textContent = '▶ Start'; }
                            })
                            .catch(function() { checks++; });
                    }, 2000);
                })
                .catch(e => { alert('Error: ' + e); btn.disabled = false; btn.textContent = '▶ Start'; });
        }
        
        function stopBot(botId) {
            if (!confirm('Stop bot ' + botId + '?')) return;
            var badge = document.querySelector('[data-bot-id="' + botId + '"] .status-badge');
            if (badge) { badge.textContent = 'stopping...'; badge.className = 'status-badge status-stopped'; }
            var btn = event.target; btn.disabled = true; btn.textContent = '⏳ Stopping...';
            fetch('/api/bots/' + botId + '/stop', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    alert(data.message || 'Bot stopped');
                    location.reload();
                })
                .catch(e => { alert('Error: ' + e); btn.disabled = false; btn.textContent = '⏹ Stop'; });
        }
        
        function pauseBot(botId) {
            fetch('/api/bots/' + botId + '/pause', {method: 'POST'})
                .then(r => r.json())
                .then(data => location.reload());
        }
        
        function editBot(botId) {
            window.location.href = '/bots/' + botId + '/edit';
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
        
        // Logs functions
        let currentLogBotId = '';
        
        function showLogs(botId) {
            currentLogBotId = botId;
            document.getElementById('logsBotName').textContent = botId;
            document.getElementById('logsModal').style.display = 'block';
            refreshLogs();
        }
        
        function closeLogs() {
            document.getElementById('logsModal').style.display = 'none';
        }
        
        function refreshLogs() {
            if (!currentLogBotId) return;
            
            fetch('/api/bots/' + currentLogBotId + '/logs?lines=100')
                .then(r => r.json())
                .then(data => {
                    const logs = data.logs || ['No logs available'];
                    document.getElementById('logsContent').textContent = logs.join('\\n');
                })
                .catch(e => {
                    document.getElementById('logsContent').textContent = 'Error loading logs: ' + e;
                });
        }
        
        function clearLogs() {
            document.getElementById('logsContent').textContent = 'Logs cleared. Click 🔄 Обновить to load new logs.';
        }
        
        // Close modal on outside click
        window.onclick = function(event) {
            const modal = document.getElementById('logsModal');
            if (event.target == modal) {
                closeLogs();
            }
        }
        
        // Auto-refresh status every 15 seconds (without killing JS)
        setInterval(function() {
            fetch('/api/bots')
                .then(r => r.json())
                .then(bots => {
                    bots.forEach(function(bot) {
                        var badge = document.querySelector('[data-bot-id="' + bot.bot_id + '"] .status-badge');
                        if (badge) {
                            badge.textContent = bot.status;
                            badge.className = 'status-badge status-' + bot.status;
                        }
                    });
                });
        }, 15000);
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
    """Start a bot (async - returns immediately, bot starts in background)"""
    import threading
    
    bot = manager.bots.get(bot_id)
    if not bot:
        return jsonify({'success': False, 'bot_id': bot_id, 'message': 'Bot not found'}), 404
    
    if bot.status.value == 'running':
        return jsonify({'success': True, 'bot_id': bot_id, 'status': 'running', 'message': 'Bot already running'})
    
    # Check API conflict
    my_key = bot.config.get('api', {}).get('key', '')
    for other_id, other_bot in manager.bots.items():
        if other_id == bot_id:
            continue
        if other_bot.status.value == 'running':
            other_key = other_bot.config.get('api', {}).get('key', '')
            if other_key == my_key:
                return jsonify({
                    'success': False, 
                    'bot_id': bot_id, 
                    'message': 'API CONFLICT: Bot ' + other_id + ' already uses same API key! Stop it first.'
                })
    
    # Start in background thread so HTTP response returns immediately
    def _start_async():
        try:
            manager.start_bot(bot_id)
        except Exception as e:
            logger.error(f"Async start error for {bot_id}: {e}")
    
    bot.status = type(bot.status).STARTING if hasattr(type(bot.status), 'STARTING') else bot.status
    thread = threading.Thread(target=_start_async, daemon=True)
    thread.start()
    
    return jsonify({
        'success': True,
        'bot_id': bot_id,
        'status': 'starting',
        'message': 'Bot starting... Check status in a few seconds'
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


@app.route('/api/bots/<bot_id>/config', methods=['GET'])
def get_bot_config_full(bot_id):
    """Get full bot configuration for editing"""
    try:
        import json
        config_path = f'bot_configs/{bot_id}.json'
        with open(config_path, 'r') as f:
            config = json.load(f)
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bots/<bot_id>/config', methods=['PUT'])
def update_bot_config_full(bot_id):
    """Update full bot configuration with restart"""
    try:
        import json
        data = request.json
        
        # Save new config
        config_path = f'bot_configs/{bot_id}.json'
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Reload config in bot manager
        manager.reload_bot_config(bot_id)
        
        return jsonify({
            'success': True, 
            'message': 'Config saved and reloaded'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bots/<bot_id>/graceful-shutdown', methods=['POST'])
def graceful_shutdown_bot(bot_id):
    """Graceful shutdown - close all positions then stop"""
    try:
        bot = manager.bots.get(bot_id)
        if not bot:
            return jsonify({'success': False, 'error': 'Bot not found'}), 404
        
        # Get positions to close
        positions = bot.engine.position_manager.get_all_positions() if bot.engine else []
        
        # Close all positions
        closed_positions = []
        for symbol in list(positions.keys()):
            try:
                bot.engine.close_position(symbol)
                closed_positions.append(symbol)
            except Exception as e:
                logger.error(f"Failed to close {symbol}: {e}")
        
        # Wait a moment for orders to process
        import time
        time.sleep(2)
        
        # Stop the bot
        manager.stop_bot(bot_id)
        
        return jsonify({
            'success': True,
            'closed_positions': closed_positions,
            'message': f'Closed {len(closed_positions)} positions and stopped bot'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bots/<bot_id>/reset-balance', methods=['POST'])
def reset_bot_balance(bot_id):
    """Reset balance to 100,000 USDT and save session stats"""
    try:
        import json
        import datetime
        
        bot = manager.bots.get(bot_id)
        if not bot:
            return jsonify({'success': False, 'error': 'Bot not found'}), 404
        
        # Get current stats before reset
        stats = {
            'bot_id': bot_id,
            'timestamp': datetime.datetime.now().isoformat(),
            'final_balance': bot.stats.total_pnl if hasattr(bot, 'stats') else 0,
            'total_trades': bot.stats.total_trades if hasattr(bot, 'stats') else 0,
            'win_rate': bot.stats.win_rate if hasattr(bot, 'stats') else 0,
            'uptime_seconds': bot.stats.uptime_seconds if hasattr(bot, 'stats') else 0
        }
        
        # Save to history
        history_file = f'bot_configs/{bot_id}_history.json'
        try:
            with open(history_file, 'r') as f:
                history = json.load(f)
        except:
            history = {'sessions': []}
        
        history['sessions'].append(stats)
        
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)
        
        # Reset stats
        if hasattr(bot, 'stats'):
            bot.stats.total_pnl = 0
            bot.stats.total_trades = 0
            bot.stats.win_rate = 0
        
        return jsonify({
            'success': True,
            'message': f'Balance reset to 100,000. Session saved to history.',
            'session_stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bots/<bot_id>/history', methods=['GET'])
def get_bot_history(bot_id):
    """Get bot session history"""
    try:
        import json
        history_file = f'bot_configs/{bot_id}_history.json'
        with open(history_file, 'r') as f:
            history = json.load(f)
        return jsonify({'success': True, 'history': history})
    except:
        return jsonify({'success': True, 'history': {'sessions': []}})


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


@app.route('/healthz', methods=['GET'])
def healthz():
    """Lightweight healthcheck endpoint for watchdog/systemd/docker probes."""
    overview = manager.get_aggregate_stats()
    payload = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "bots": overview,
    }
    if psutil:
        p = psutil.Process(os.getpid())
        payload["runtime"] = {
            "ram_mb": round(p.memory_info().rss / (1024 * 1024), 2),
            "cpu_pct": p.cpu_percent(interval=0.0),
            "threads": p.num_threads(),
            "connections": len(p.connections(kind="inet")),
        }
    return jsonify(payload)


@app.route('/bots/<bot_id>/edit')
def edit_bot_page(bot_id):
    """Full bot configuration editor - dynamic, renders ALL config fields"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit {bot_id}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: #fff;
                min-height: 100vh;
                padding: 20px;
            }}
            .header {{
                background: rgba(0,0,0,0.3);
                padding: 20px;
                border-bottom: 2px solid #00ff88;
                margin: -20px -20px 20px -20px;
            }}
            .header h1 {{ color: #00ff88; }}
            .container {{ max-width: 900px; margin: 0 auto; }}
            .section {{
                background: rgba(255,255,255,0.05);
                padding: 20px;
                border-radius: 12px;
                margin-bottom: 20px;
                border: 1px solid rgba(255,255,255,0.1);
            }}
            .section-title {{
                color: #00ff88;
                font-size: 18px;
                margin-bottom: 15px;
                padding-bottom: 10px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
                cursor: pointer;
            }}
            .section-title:hover {{ color: #33ffaa; }}
            .form-row {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 15px;
                margin-bottom: 15px;
            }}
            .form-group {{
                display: flex;
                flex-direction: column;
            }}
            .form-group label {{
                color: #888;
                font-size: 11px;
                margin-bottom: 5px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .form-group input, .form-group select, .form-group textarea {{
                padding: 10px;
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 8px;
                background: rgba(0,0,0,0.3);
                color: #fff;
                font-size: 14px;
                font-family: monospace;
            }}
            .form-group input:focus, .form-group select:focus, .form-group textarea:focus {{
                outline: none;
                border-color: #00ff88;
            }}
            .form-group textarea {{ min-height: 60px; resize: vertical; }}
            .btn {{
                padding: 15px 30px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-weight: bold;
                font-size: 16px;
                transition: all 0.2s;
            }}
            .btn:hover {{ transform: translateY(-2px); }}
            .btn-save {{ background: #00ff88; color: #000; }}
            .btn-reset {{ background: #ffaa00; color: #000; }}
            .btn-shutdown {{ background: #ff4444; color: #fff; }}
            .btn-back {{ background: #666; color: #fff; text-decoration: none; display: inline-block; }}
            .actions {{
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
                margin-top: 20px;
            }}
            .status-badge {{
                display: inline-block;
                padding: 5px 15px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: bold;
            }}
            .status-running {{ background: #00ff88; color: #000; }}
            .status-stopped {{ background: #ff4444; color: #fff; }}
            .alert {{
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
                display: none;
            }}
            .alert.success {{ background: rgba(0,255,136,0.2); border: 1px solid #00ff88; color: #00ff88; }}
            .alert.error {{ background: rgba(255,68,68,0.2); border: 1px solid #ff4444; color: #ff4444; }}
            .history-table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }}
            .history-table th, .history-table td {{
                padding: 10px;
                text-align: left;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }}
            .history-table th {{ color: #888; font-size: 12px; text-transform: uppercase; }}
            .positive {{ color: #00ff88; }}
            .negative {{ color: #ff4444; }}
            .bool-true {{ color: #00ff88; font-weight: bold; }}
            .bool-false {{ color: #ff4444; }}
            .raw-json {{
                background: rgba(0,0,0,0.4);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
                padding: 15px;
                font-family: monospace;
                font-size: 12px;
                color: #00ff88;
                white-space: pre-wrap;
                word-break: break-all;
                max-height: 400px;
                overflow: auto;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>⚙️ Edit Bot: {bot_id}</h1>
        </div>
        
        <div class="container">
            <div id="alertBox" class="alert"></div>
            
            <!-- Status -->
            <div class="section">
                <div class="section-title">📊 Текущий статус</div>
                <div id="botStatus">Загрузка...</div>
            </div>
            
            <!-- Dynamic Config Sections - rendered from JSON -->
            <div id="configSections">Загрузка конфигурации...</div>
            
            <!-- Raw JSON Editor -->
            <div class="section">
                <div class="section-title" onclick="document.getElementById('rawJsonBlock').style.display=document.getElementById('rawJsonBlock').style.display==='none'?'block':'none'">📝 Raw JSON (нажми чтобы показать/скрыть)</div>
                <div id="rawJsonBlock" style="display:none">
                    <textarea id="rawJsonEditor" class="raw-json" style="width:100%;min-height:300px"></textarea>
                    <button class="btn btn-save" style="margin-top:10px" onclick="saveRawJson()">💾 Сохранить JSON</button>
                </div>
            </div>
            
            <!-- History -->
            <div class="section">
                <div class="section-title">📈 История сессий</div>
                <div id="historyContainer">
                    <p style="color:#888">Загрузка истории...</p>
                </div>
            </div>
            
            <!-- Actions -->
            <div class="section">
                <div class="section-title">🚀 Действия</div>
                <div class="actions">
                    <button class="btn btn-save" onclick="saveConfig()">💾 Сохранить конфиг</button>
                    <button class="btn btn-reset" onclick="resetBalance()">🔄 Сбросить баланс к 100k</button>
                    <button class="btn btn-shutdown" onclick="gracefulShutdown()">🛑 Graceful Shutdown</button>
                    <a href="/" class="btn btn-back">⬅️ Назад</a>
                </div>
            </div>
        </div>
        
        <script>
            const botId = '{bot_id}';
            let fullConfig = {{}};
            
            // Section icons mapping
            const sectionIcons = {{
                'api': '🔑', 'strategy': '🎯', 'risk': '🛡️', 'trading': '⚡',
                'logging': '📋', 'symbols': '📊', 'name': '🏷️', 'enabled': '🔌'
            }};

            // Render a config value as an input field
            function renderField(key, value, path) {{
                const id = path.join('_');
                if (typeof value === 'boolean') {{
                    return '<div class="form-group"><label>' + key + '</label>' +
                        '<select id="field_' + id + '" data-path="' + path.join('.') + '">' +
                        '<option value="true"' + (value ? ' selected' : '') + '>Yes (true)</option>' +
                        '<option value="false"' + (!value ? ' selected' : '') + '>No (false)</option>' +
                        '</select></div>';
                }} else if (typeof value === 'number') {{
                    const step = Number.isInteger(value) ? '1' : '0.01';
                    return '<div class="form-group"><label>' + key + '</label>' +
                        '<input type="number" id="field_' + id + '" data-path="' + path.join('.') + '" step="' + step + '" value="' + value + '"></div>';
                }} else if (Array.isArray(value)) {{
                    return '<div class="form-group"><label>' + key + ' (array)</label>' +
                        '<textarea id="field_' + id + '" data-path="' + path.join('.') + '">' + JSON.stringify(value, null, 2) + '</textarea></div>';
                }} else {{
                    const isSecret = key.toLowerCase().includes('secret');
                    const inputType = isSecret ? 'password' : 'text';
                    return '<div class="form-group"><label>' + key + '</label>' +
                        '<input type="' + inputType + '" id="field_' + id + '" data-path="' + path.join('.') + '" value="' + (value || '') + '"></div>';
                }}
            }}

            // Build config sections dynamically from JSON
            function buildConfigUI(config) {{
                let html = '';
                const skipKeys = ['bot_id'];
                
                for (const [key, value] of Object.entries(config)) {{
                    if (skipKeys.includes(key)) continue;
                    
                    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {{
                        // Object section
                        const icon = sectionIcons[key] || '📁';
                        html += '<div class="section">';
                        html += '<div class="section-title">' + icon + ' ' + key.charAt(0).toUpperCase() + key.slice(1) + '</div>';
                        html += '<div class="form-row">';
                        for (const [subKey, subValue] of Object.entries(value)) {{
                            if (typeof subValue === 'object' && subValue !== null && !Array.isArray(subValue)) {{
                                // Nested object - flatten
                                for (const [k3, v3] of Object.entries(subValue)) {{
                                    html += renderField(subKey + '.' + k3, v3, [key, subKey, k3]);
                                }}
                            }} else {{
                                html += renderField(subKey, subValue, [key, subKey]);
                            }}
                        }}
                        html += '</div></div>';
                    }} else {{
                        // Top-level value (like enabled, name)
                        const icon = sectionIcons[key] || '⚙️';
                        if (!html.startsWith('<div class="section"')) {{
                            html += '<div class="section">';
                            html += '<div class="section-title">⚙️ Основные настройки</div>';
                            html += '<div class="form-row">';
                        }}
                        html += renderField(key, value, [key]);
                    }}
                }}
                
                // Close any open section
                if (html.includes('<div class="form-row">') && !html.includes('</div></div>')) {{
                    html += '</div></div>';
                }}
                
                return html;
            }}

            // Collect all field values back into config object
            function collectConfig() {{
                const config = JSON.parse(JSON.stringify(fullConfig));
                const fields = document.querySelectorAll('[data-path]');
                fields.forEach(function(field) {{
                    const path = field.getAttribute('data-path').split('.');
                    let val = field.value;
                    
                    // Parse value type
                    if (field.tagName === 'SELECT') {{
                        val = val === 'true';
                    }} else if (field.type === 'number') {{
                        val = parseFloat(val);
                    }} else if (field.tagName === 'TEXTAREA') {{
                        try {{ val = JSON.parse(val); }} catch(e) {{}}
                    }}
                    
                    // Set value in config by path
                    let obj = config;
                    for (let i = 0; i < path.length - 1; i++) {{
                        if (!obj[path[i]]) obj[path[i]] = {{}};
                        obj = obj[path[i]];
                    }}
                    obj[path[path.length - 1]] = val;
                }});
                return config;
            }}

            // Load config on page load
            async function loadConfig() {{
                try {{
                    const response = await fetch('/api/bots/' + botId + '/config');
                    const data = await response.json();
                    
                    if (data.success) {{
                        fullConfig = data.config;
                        
                        // Build dynamic UI
                        document.getElementById('configSections').innerHTML = buildConfigUI(fullConfig);
                        
                        // Set raw JSON
                        document.getElementById('rawJsonEditor').value = JSON.stringify(fullConfig, null, 2);
                        
                        // Status
                        const c = fullConfig;
                        document.getElementById('botStatus').innerHTML =
                            '<span class="status-badge ' + (c.enabled ? 'status-running' : 'status-stopped') + '">' +
                            (c.enabled ? 'ENABLED' : 'DISABLED') + '</span>' +
                            '<span style="margin-left:15px; color:#888">' + (c.name || botId) + '</span>';
                    }}
                }} catch (e) {{
                    showAlert('Error loading config: ' + e, 'error');
                }}
            }}
            
            // Load history
            async function loadHistory() {{
                try {{
                    const response = await fetch('/api/bots/' + botId + '/history');
                    const data = await response.json();
                    
                    if (data.success && data.history.sessions.length > 0) {{
                        let html = '<table class="history-table"><tr><th>Дата</th><th>PnL</th><th>Сделок</th><th>Win Rate</th><th>Аптайм</th></tr>';
                        data.history.sessions.slice().reverse().forEach(function(s) {{
                            const pnl = parseFloat(s.final_balance);
                            const pnlClass = pnl >= 0 ? 'positive' : 'negative';
                            const pnlSign = pnl >= 0 ? '+' : '';
                            html += '<tr>' +
                                '<td>' + new Date(s.timestamp).toLocaleString() + '</td>' +
                                '<td class="' + pnlClass + '">' + pnlSign + pnl.toFixed(2) + ' USDT</td>' +
                                '<td>' + s.total_trades + '</td>' +
                                '<td>' + (s.win_rate * 100).toFixed(1) + '%</td>' +
                                '<td>' + Math.floor(s.uptime_seconds / 60) + ' мин</td>' +
                                '</tr>';
                        }});
                        html += '</table>';
                        document.getElementById('historyContainer').innerHTML = html;
                    }} else {{
                        document.getElementById('historyContainer').innerHTML = '<p style="color:#888">Нет сохраненных сессий</p>';
                    }}
                }} catch (e) {{
                    document.getElementById('historyContainer').innerHTML = '<p style="color:#ff4444">Ошибка загрузки истории</p>';
                }}
            }}
            
            // Save config from dynamic fields
            async function saveConfig() {{
                const config = collectConfig();
                
                try {{
                    const response = await fetch('/api/bots/' + botId + '/config', {{
                        method: 'PUT',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(config)
                    }});
                    const data = await response.json();
                    
                    if (data.success) {{
                        showAlert('✅ Конфигурация сохранена! Перезапусти бота для применения.', 'success');
                    }} else {{
                        showAlert('❌ Ошибка: ' + data.error, 'error');
                    }}
                }} catch (e) {{
                    showAlert('❌ Ошибка сохранения: ' + e, 'error');
                }}
            }}

            // Save raw JSON
            async function saveRawJson() {{
                try {{
                    const config = JSON.parse(document.getElementById('rawJsonEditor').value);
                    const response = await fetch('/api/bots/' + botId + '/config', {{
                        method: 'PUT',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(config)
                    }});
                    const data = await response.json();
                    
                    if (data.success) {{
                        showAlert('✅ JSON сохранён! Перезапусти бота для применения.', 'success');
                        loadConfig(); // Refresh UI
                    }} else {{
                        showAlert('❌ Ошибка: ' + data.error, 'error');
                    }}
                }} catch (e) {{
                    showAlert('❌ Невалидный JSON: ' + e, 'error');
                }}
            }}
            
            // Reset balance
            async function resetBalance() {{
                if (!confirm('Сбросить баланс к 100,000 USDT? Текущая статистика будет сохранена в историю.')) return;
                
                try {{
                    const response = await fetch('/api/bots/' + botId + '/reset-balance', {{method: 'POST'}});
                    const data = await response.json();
                    
                    if (data.success) {{
                        showAlert('✅ Баланс сброшен! PnL сессии: $' + data.session_stats.final_balance.toFixed(2) + ' USDT', 'success');
                        loadHistory();
                    }} else {{
                        showAlert('❌ Ошибка: ' + data.error, 'error');
                    }}
                }} catch (e) {{
                    showAlert('❌ Ошибка: ' + e, 'error');
                }}
            }}
            
            // Graceful shutdown
            async function gracefulShutdown() {{
                if (!confirm('Graceful shutdown? Все позиции будут закрыты перед остановкой.')) return;
                
                try {{
                    const response = await fetch('/api/bots/' + botId + '/graceful-shutdown', {{method: 'POST'}});
                    const data = await response.json();
                    
                    if (data.success) {{
                        showAlert('✅ Бот остановлен. Закрыто позиций: ' + data.closed_positions.length, 'success');
                    }} else {{
                        showAlert('❌ Ошибка: ' + data.error, 'error');
                    }}
                }} catch (e) {{
                    showAlert('❌ Ошибка: ' + e, 'error');
                }}
            }}
            
            // Show alert
            function showAlert(message, type) {{
                const box = document.getElementById('alertBox');
                box.textContent = message;
                box.className = 'alert ' + type;
                box.style.display = 'block';
                setTimeout(function() {{ box.style.display = 'none'; }}, 5000);
            }}
            
            // Load on start
            loadConfig();
            loadHistory();
        </script>
    </body>
    </html>
    """


def start_dashboard(host='0.0.0.0', port=5001):
    """Start the multi-bot dashboard"""
    logger.info(f"Starting Multi-Bot Dashboard on http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    start_dashboard()
