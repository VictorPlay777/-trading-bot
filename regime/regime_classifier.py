import numpy as np


class RegimeClassifier:
    def classify(self, df):
        ret = df["close"].pct_change().dropna()
        vol5 = float(ret.rolling(5).std().iloc[-1]) if len(ret) >= 10 else 0.0
        vol20 = float(ret.rolling(20).std().iloc[-1]) if len(ret) >= 30 else vol5
        trend = float((df["close"].ewm(span=20, adjust=False).mean().iloc[-1] -
                       df["close"].ewm(span=50, adjust=False).mean().iloc[-1]) / (df["close"].iloc[-1] + 1e-12))
        if vol5 > vol20 * 2.2:
            return "panic"
        if abs(trend) > 0.004 and vol5 > vol20 * 0.9:
            return "trend"
        if vol5 > vol20 * 1.3:
            return "breakout"
        return "chop"

