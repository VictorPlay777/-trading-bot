# Real-Time Quant Fund Engine

A production-grade Python system for high-frequency crypto futures trading on Bybit. Trades up to 250 symbols simultaneously with adaptive capital allocation, micro-scalping strategies, and survival-based coin selection.

## Architecture

The system consists of 4 main threads:

1. **Market Stream** - WebSocket ingestion for 250+ symbols (orderbook, trades, funding, volume)
2. **Signal Engine** - Micro-strategies (scalp/momentum/mean reversion) generating real-time signals
3. **Capital Allocator** - Rebalances capital every 5 seconds based on health scores
4. **Survival Engine** - Blacklists underperforming coins with cooldown system

## Components

### Engine Modules

- `market_data.py` - WebSocket data ingestion for 250+ symbols
- `signal_engine.py` - 3 strategies: momentum, mean reversion, breakout
- `scoring.py` - Health score calculation (PnL, volume, volatility, momentum)
- `portfolio.py` - Capital allocation and rebalancing
- `survival.py` - Blacklist and cooldown system
- `execution.py` - Adaptive TP/SL and order execution
- `risk.py` - Global drawdown protection and leverage scaling

## Installation

```bash
cd quant_engine
pip install -r requirements.txt
```

## Configuration

All parameters are controlled via `config.yaml`:

```yaml
mode: "REALTIME_PROP_FUND"
initial_universe_size: 250
max_active_coins: 250

# Execution
execution:
  type: "hybrid"
  min_order_delay_ms: 200
  max_slippage_pct: 0.15

# TP/SL (Micro Scalping)
risk:
  base_tp_pct: 0.25
  base_sl_pct: 0.12
  atr_multiplier_tp: 1.2
  atr_multiplier_sl: 0.7

# Portfolio
portfolio:
  rebalance_interval_sec: 5
  capital_concentration_limit: 0.25

# Survival
health:
  enable_survival_mode: true
  loss_streak_blacklist: 4
  blacklist_duration_minutes: 1440

# Risk
risk_engine:
  global_drawdown_cutoff: -0.08
  leverage_scaling: true
  max_leverage: 5
```

## Usage

### Set Environment Variables

```bash
export BYBIT_API_KEY="your_api_key"
export BYBIT_API_SECRET="your_api_secret"
```

### Run on Testnet

```bash
python main.py
```

The system defaults to testnet. To use production, modify `testnet=False` in `main.py`.

## Key Features

### 1. No Initial Filtering
- All 250 symbols start active
- Survival engine filters out underperformers over time

### 2. Adaptive Capital Allocation
- Capital flows to top 20-60 coins based on health scores
- Rebalances every 5 seconds
- Max 25% capital per coin

### 3. Survival System
- Loss streak of 4 trades → 24h blacklist
- Automatic cooldown expiry
- Recovery tracking

### 4. Micro-Scalping
- TP: 0.25% base or ATR-based
- SL: 0.12% base or ATR-based
- High frequency, low latency

### 5. Risk Management
- Global drawdown cutoff at -8%
- Dynamic leverage scaling (1x-5x)
- Emergency stop in severe drawdown

## Scoring System

Health score = weighted combination of:
- PnL score (weight: 2.0)
- Volume score (weight: 1.5)
- Volatility score (weight: 1.2)
- Momentum score (weight: 2.0)

## Logging

All trades, skips, rebalances, and blacklist events are logged to `quant_engine.log`.

## Monitoring

The system logs status every second including:
- Current capital
- Drawdown percentage
- Number of active positions
- Blacklisted symbol count

## Important Notes

- **Production Use**: Requires proper API signature implementation (HMAC-SHA256)
- **Testnet First**: Always test on testnet before production
- **Risk Limits**: Adjust drawdown cutoff and leverage based on risk tolerance
- **Symbol Universe**: Can be adjusted via `initial_universe_size` in config

## File Structure

```
quant_engine/
├── engine/
│   ├── market_data.py
│   ├── signal_engine.py
│   ├── scoring.py
│   ├── portfolio.py
│   ├── survival.py
│   ├── execution.py
│   └── risk.py
├── config.yaml
├── main.py
├── requirements.txt
└── README.md
```

## License

Proprietary trading system. Use at your own risk.
