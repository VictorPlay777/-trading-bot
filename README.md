# Bybit Futures Trend-Following Trading Bot

Professional-grade crypto futures trading bot for Bybit testnet. Trend-following strategy with strict regime filters and institutional-style risk management.

## Architecture

```
trading-bot/
├── main.py              # Async event loop & orchestration
├── api_client.py        # Bybit V5 REST API wrapper
├── market_data.py       # Candles, caching, OHLCV management
├── indicators.py        # EMA, RSI, ATR, ADX calculations
├── regime_detector.py   # Trend vs Chop classification
├── strategy.py          # Entry/exit signal logic (pure signal layer)
├── risk_manager.py      # Position sizing, SL/TP, daily limits
├── execution.py         # Order placement with retry logic
├── portfolio.py         # Position tracking, PnL, trade logging
├── config.py            # Centralized configuration
├── logger.py            # Structured logging + CSV trade log
└── requirements.txt     # Dependencies
```

## Strategy Overview

### Market Regime Filter (CRITICAL)
- **TREND MODE** (Trading Allowed): ADX > 25, EMAs aligned, no whipsaw
- **CHOP MODE** (No Trading): ADX < 20, whipsaw detected, flat EMAs

### Entry Conditions

**LONG Entry:**
- Trend mode = TRUE
- EMA20 > EMA50
- Price > EMA200
- Pullback to EMA20/50
- RSI 45-65
- Bullish candle confirmation

**SHORT Entry:**
- Trend mode = TRUE
- EMA20 < EMA50
- Price < EMA200
- Pullback to EMA20/50
- RSI 35-55
- Bearish candle confirmation

### Risk Management
- Risk per trade: 0.25% - 1% max
- Dynamic leverage (adaptive to volatility)
- ATR-based stop loss (1.5-2x ATR)
- Minimum RR 1:1.5, preferred 1:2-1:3
- Daily loss limit: 3%
- Max consecutive losses: 3 → 4h pause
- Max open positions: 1

### Fee Model (Realistic PnL)
- Entry fee: 0.06% (taker)
- Exit fee: 0.06% (taker)
- Funding: 0.01% per 8h
- Slippage: 0.1%
- Net PnL = Gross - All fees

## Usage

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure (Optional)
Edit `config.py` to adjust parameters:
- `symbol` - Trading pair (default: BTCUSDT)
- `timeframe` - Candle interval (default: 15m)
- `risk_per_trade_pct` - Risk per trade (default: 0.5%)
- `max_leverage` - Max leverage (default: 100x)

### 3. Run
```bash
python main.py
```

## Logs

### Console Output
Real-time status updates with:
- Current price
- Market regime (trend/chop)
- ADX value
- Position status
- PnL updates
- Signal generation

### Trade Log CSV
All trades logged to `logs/trades.csv` with:
- Entry/exit timestamps
- Direction & size
- Entry/exit prices
- Gross & net PnL
- All fees (entry, exit, funding)
- ROI percentage
- Regime at entry
- Indicator values at entry
- Exit reason

### Structured JSON Logs
Full operation logs in `logs/bot.log` (JSON format) for analysis.

## Key Design Principles

1. **HOLD is default** - Bot does nothing most of the time
2. **No trade > Bad trade** - Quality over quantity
3. **Survival first** - Risk management prioritizes capital preservation
4. **Institutional style** - Modular, testable, extensible
5. **Realistic fees** - All costs accounted in PnL

## Safety Features

- Trading pauses after 3 consecutive losses
- Daily loss limit killswitch (3%)
- Duplicate order prevention (idempotency)
- Order confirmation verification
- Position state syncing with exchange
- Leverage adjustment based on volatility

## Extending

The modular design allows easy extension:
- **ML integration**: Add prediction model in `strategy.py`
- **Multi-symbol**: Extend `portfolio.py` for multi-asset
- **Advanced execution**: Add TWAP/VWAP in `execution.py`
- **More indicators**: Extend `indicators.py`

## Warning

⚠️ This is a testnet trading bot. Always test thoroughly before using real funds. High leverage (100x) carries extreme risk of liquidation.

## License

MIT - Use at your own risk.
