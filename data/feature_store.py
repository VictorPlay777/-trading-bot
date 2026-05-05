import numpy as np


def _ema(s, p):
    return s.ewm(span=p, adjust=False).mean()


class FeatureStore:
    def build(self, df, orderbook: dict, funding: float = 0.0, oi_delta: float = 0.0):
        x = {}
        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]
        x["ret_1"] = float(c.pct_change().iloc[-1])
        x["ret_3"] = float(c.pct_change(3).iloc[-1])
        x["ema_slope_20"] = float((_ema(c, 20).iloc[-1] - _ema(c, 20).iloc[-5]) / (c.iloc[-1] + 1e-12))
        x["ema_slope_50"] = float((_ema(c, 50).iloc[-1] - _ema(c, 50).iloc[-5]) / (c.iloc[-1] + 1e-12))
        body = (df["close"] - df["open"]).abs()
        wick = (h - l) - body
        x["wick_body_ratio"] = float((wick.iloc[-1] + 1e-12) / (body.iloc[-1] + 1e-12))
        x["rel_volume"] = float(v.iloc[-1] / (v.rolling(20).mean().iloc[-1] + 1e-12))
        x["vol_compression"] = float(c.pct_change().rolling(20).std().iloc[-1])
        x["vol_expansion"] = float(c.pct_change().rolling(5).std().iloc[-1])
        x["momentum_accel"] = float(c.diff().diff().iloc[-1] / (c.iloc[-1] + 1e-12))
        x["orderbook_imbalance"] = float(orderbook.get("imbalance", 0.0))
        x["spread_bps"] = float(orderbook.get("spread_bps", 999.0))
        x["depth_usdt"] = float(orderbook.get("depth_usdt", 0.0))
        x["funding_rate"] = float(funding)
        x["oi_delta"] = float(oi_delta)
        return x

