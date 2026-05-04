class QualityGate:
    def __init__(self, min_score=0.70):
        self.min_score = min_score

    def score(self, model_confidence, trend_alignment, liquidity_quality, spread_quality, regime_quality, volatility_quality, orderbook_imbalance):
        w = (0.25, 0.15, 0.15, 0.10, 0.10, 0.10, 0.15)
        s = (
            w[0] * model_confidence +
            w[1] * trend_alignment +
            w[2] * liquidity_quality +
            w[3] * spread_quality +
            w[4] * regime_quality +
            w[5] * volatility_quality +
            w[6] * orderbook_imbalance
        )
        return max(0.0, min(1.0, s))

    def allow(self, score: float):
        return score >= self.min_score

