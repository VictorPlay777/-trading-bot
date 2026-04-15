"""
Analyze Bybit linear futures symbols to select top 10 most volatile coins not in current list
"""
import sys
from api_client import BybitClient
from config import trading_config

def analyze_volatility():
    """Analyze all linear futures symbols and select top 10 most volatile not in current list"""
    print("=" * 60)
    print("ANALYZING BYBIT LINEAR FUTURES - VOLATILITY")
    print("=" * 60)

    api = BybitClient()

    # Get current symbols
    current_symbols = set(trading_config.symbols)
    print(f"Current symbols: {len(current_symbols)}")
    for symbol in sorted(current_symbols):
        print(f"  {symbol}")

    # Get all tickers
    print("\nFetching all linear futures tickers...")
    tickers = api.get_all_linear_tickers()
    print(f"Total symbols found: {len(tickers)}")

    # Filter and analyze
    analyzed = []
    for ticker in tickers:
        symbol = ticker.get("symbol")
        if not symbol or not symbol.endswith("USDT"):
            continue

        # Skip if already in current list
        if symbol in current_symbols:
            continue

        # Skip if no volume data (need liquidity)
        volume_24h = float(ticker.get("volume24h", 0) or 0)
        turnover_24h = float(ticker.get("turnover24h", 0) or 0)
        price = float(ticker.get("lastPrice", 0) or 0)

        if volume_24h == 0 or price == 0:
            continue

        # Skip low liquidity (less than $1M turnover)
        if turnover_24h < 1000000:
            continue

        # Calculate volatility (high - low) / price
        high_24h = float(ticker.get("highPrice24h", 0) or 0)
        low_24h = float(ticker.get("lowPrice24h", 0) or 0)

        if high_24h > 0 and low_24h > 0:
            volatility = (high_24h - low_24h) / price
        else:
            continue

        analyzed.append({
            "symbol": symbol,
            "volume_24h": volume_24h,
            "turnover_24h": turnover_24h,
            "price": price,
            "volatility": volatility,
            "high_24h": high_24h,
            "low_24h": low_24h
        })

    print(f"Valid USDT symbols not in current list with liquidity: {len(analyzed)}")

    # Sort by volatility (descending)
    by_volatility = sorted(analyzed, key=lambda x: x["volatility"], reverse=True)
    top_10_volatility = by_volatility[:10]

    print("\n" + "=" * 60)
    print("TOP 10 MOST VOLATILE COINS (not in current list)")
    print("=" * 60)
    for i, item in enumerate(top_10_volatility, 1):
        print(f"{i:2d}. {item['symbol']:12s} | Volatility: {item['volatility']:.2%} | Vol: ${item['turnover_24h']:>15,.0f} | Price: ${item['price']:>8.2f}")

    # Generate config snippet
    print("\n" + "=" * 60)
    print("NEW SYMBOLS TO ADD")
    print("=" * 60)
    new_symbols = [item["symbol"] for item in top_10_volatility]
    for symbol in new_symbols:
        print(f"  {symbol}")

    print("\n" + "=" * 60)
    print("UPDATED SYMBOLS LIST (current + new)")
    print("=" * 60)
    updated_symbols = sorted(list(current_symbols) + new_symbols)
    print("symbols = [")
    for symbol in updated_symbols:
        print(f'    "{symbol}",')
    print("]")

    print("\n" + "=" * 60)
    print("MAX LEVERAGE FOR NEW SYMBOLS (need to check instruments info)")
    print("=" * 60)
    print("symbol_max_leverage = {")
    # Add existing
    for symbol in sorted(current_symbols):
        existing_lev = trading_config.symbol_max_leverage.get(symbol, 100)
        print(f'    "{symbol}": {existing_lev},')
    # Add new (default 100, need to update)
    for symbol in new_symbols:
        print(f'    "{symbol}": 100,  # TODO: update with actual max leverage')
    print("}")

if __name__ == "__main__":
    analyze_volatility()
