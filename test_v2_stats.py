"""
Test script for v2 professional statistics system
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stats import (
    SystemIDGenerator,
    SignalLogger,
    TradeLogger,
    EquityTracker,
    MAEMFETracker,
    DataQualityChecker,
    AdvancedMetricsCalculator
)
import time

def test_system_id_generator():
    """Test ID generation"""
    print("Testing SystemIDGenerator...")
    
    signal_id = SystemIDGenerator.generate_signal_id()
    print(f"  Signal ID: {signal_id}")
    
    trade_id = SystemIDGenerator.generate_trade_id("BTCUSDT", time.time())
    print(f"  Trade ID: {trade_id}")
    
    equity_id = SystemIDGenerator.generate_equity_snapshot_id()
    print(f"  Equity ID: {equity_id}")
    
    print("[OK] SystemIDGenerator works!")

def test_signal_logger():
    """Test signal logging"""
    print("\nTesting SignalLogger...")
    
    signal_logger = SignalLogger(logs_dir="logs")
    
    test_signal = {
        "timestamp": time.time(),
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "direction": "long",
        "confidence": 0.75,
        "strategy_version": "v2_test",
        "model_version": "catboost_v1",
        "feature_version": "v2",
        "regime": "trend",
        "entry": 50000.0,
        "full_features": {
            "ret_1": 0.001,
            "ret_3": 0.002,
            "ema_slope_20": 0.0001,
            "ema_slope_50": 0.0002,
            "wick_body_ratio": 0.5,
            "rel_volume": 1.2,
            "vol_compression": 0.001,
            "vol_expansion": 0.002,
            "momentum_accel": 0.0001,
            "orderbook_imbalance": 0.6,
            "spread_bps": 2.0,
            "depth_usdt": 100000.0,
            "funding_rate": 0.0001,
            "oi_delta": 100.0
        }
    }
    
    signal_id = signal_logger.log_signal(test_signal, "ACCEPTED", "All filters passed")
    print(f"  Signal logged with ID: {signal_id}")
    
    print("[OK] SignalLogger works!")

def test_trade_logger():
    """Test trade logging"""
    print("\nTesting TradeLogger...")
    
    trade_logger = TradeLogger(logs_dir="logs")
    
    test_trade = {
        "signal_id": "test_signal_id",
        "strategy_version": "v2_test",
        "model_version": "catboost_v1",
        "feature_version": "v2",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "side": "long",
        "signal_timestamp": time.time() - 300,
        "entry_timestamp": time.time() - 290,
        "exit_timestamp": time.time(),
        "entry_price": 50000.0,
        "exit_price": 50100.0,
        "quantity": 0.2,
        "stop_loss": 49800.0,
        "take_profit": 50200.0,
        "exit_reason": "tp1_full",
        "holding_time": 290.0,
        "gross_pnl": 20.0,
        "commission": 10.0,
        "funding": 1.0,
        "slippage": 0.5,
        "spread_cost": 0.5,
        "net_pnl": 8.0,
        "risk_amount": 200.0,
        "mae": -50.0,
        "mae_pct": -0.1,
        "mae_r": -0.25,
        "mfe": 150.0,
        "mfe_pct": 0.3,
        "mfe_r": 0.75,
        "equity_at_entry": 100000.0,
        "equity_at_exit": 100008.0
    }
    
    trade_id = trade_logger.log_trade(test_trade)
    print(f"  Trade logged with ID: {trade_id}")
    
    print("[OK] TradeLogger works!")

def test_equity_tracker():
    """Test equity tracking"""
    print("\nTesting EquityTracker...")
    
    equity_tracker = EquityTracker(logs_dir="logs")
    
    test_equity = {
        "balance": 100000.0,
        "equity": 100000.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "open_positions": 0,
        "gross_exposure": 0.0,
        "net_exposure": 0.0
    }
    
    snapshot_id = equity_tracker.log_snapshot(test_equity)
    print(f"  Equity snapshot logged with ID: {snapshot_id}")
    
    print("[OK] EquityTracker works!")

def test_mae_mfe_tracker():
    """Test MAE/MFE tracking"""
    print("\nTesting MAEMFETracker...")
    
    mae_mfe_tracker = MAEMFETracker()
    
    # Register position
    mae_mfe_tracker.register_position("BTCUSDT", 50000.0, "long", time.time())
    
    # Update with some price movements
    mae_mfe_tracker.update_position("BTCUSDT", 50050.0)  # +50 (favorable)
    mae_mfe_tracker.update_position("BTCUSDT", 49950.0)  # -50 (adverse)
    mae_mfe_tracker.update_position("BTCUSDT", 50100.0)  # +100 (favorable)
    
    # Close position
    metrics = mae_mfe_tracker.close_position("BTCUSDT", 50100.0)
    
    print(f"  MAE: {metrics['mae']:.2f}, MAE%: {metrics['mae_pct']:.2f}%, MAE_R: {metrics['mae_r']:.2f}")
    print(f"  MFE: {metrics['mfe']:.2f}, MFE%: {metrics['mfe_pct']:.2f}%, MFE_R: {metrics['mfe_r']:.2f}")
    
    print("[OK] MAEMFETracker works!")

def test_data_quality():
    """Test data quality checking"""
    print("\nTesting DataQualityChecker...")
    
    data_quality = DataQualityChecker(logs_dir="logs")
    
    # Test valid signal
    valid_signal = {
        "signal_id": "test_signal_123",
        "timestamp": time.time(),
        "symbol": "BTCUSDT",
        "direction": "long",
        "decision": "ACCEPTED",
        "decision_timestamp": time.time()
    }
    
    is_valid = data_quality.validate_signal_record(valid_signal)
    print(f"  Valid signal validation: {is_valid}")
    
    # Test invalid signal
    invalid_signal = {
        "signal_id": "test_signal_456",
        "timestamp": -1,  # Invalid timestamp
        "symbol": "BTCUSDT",
        "direction": "invalid",  # Invalid direction
        "decision": "ACCEPTED",
        "decision_timestamp": time.time()
    }
    
    is_valid = data_quality.validate_signal_record(invalid_signal)
    print(f"  Invalid signal validation: {is_valid}")
    
    print(f"  Total errors: {len(data_quality.get_errors())}")
    
    print("[OK] DataQualityChecker works!")

def test_advanced_metrics():
    """Test advanced metrics calculation"""
    print("\nTesting AdvancedMetricsCalculator...")
    
    metrics_calculator = AdvancedMetricsCalculator(logs_dir="logs")
    
    # Create sample trades
    sample_trades = [
        {
            "net_pnl": 100.0,
            "gross_pnl": 110.0,
            "holding_time": 300.0,
            "r_multiple": 1.5
        },
        {
            "net_pnl": -50.0,
            "gross_pnl": -45.0,
            "holding_time": 150.0,
            "r_multiple": -0.75
        },
        {
            "net_pnl": 75.0,
            "gross_pnl": 85.0,
            "holding_time": 200.0,
            "r_multiple": 1.0
        }
    ]
    
    trade_stats = metrics_calculator.calculate_trade_statistics(sample_trades)
    
    print(f"  Total trades: {trade_stats['total_trades']}")
    print(f"  Win rate: {trade_stats['win_rate']:.2%}")
    print(f"  Net profit: ${trade_stats['net_profit']:.2f}")
    print(f"  Profit factor: {trade_stats['profit_factor']:.2f}")
    print(f"  Expectancy: ${trade_stats['expectancy']:.2f}")
    
    print("[OK] AdvancedMetricsCalculator works!")

if __name__ == "__main__":
    print("=" * 60)
    print("V2 PROFESSIONAL STATISTICS SYSTEM TEST")
    print("=" * 60)
    
    try:
        test_system_id_generator()
        test_signal_logger()
        test_trade_logger()
        test_equity_tracker()
        test_mae_mfe_tracker()
        test_data_quality()
        test_advanced_metrics()
        
        print("\n" + "=" * 60)
        print("[OK] ALL TESTS PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()