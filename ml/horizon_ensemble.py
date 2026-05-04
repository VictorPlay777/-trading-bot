class HorizonEnsemble:
    def __init__(self, horizons):
        self.horizons = horizons

    def vote(self, horizon_probs: dict, regime: str):
        weights = {h: 1.0 for h in self.horizons}
        if regime == "trend":
            for h in self.horizons:
                weights[h] = 1.2 if h >= 5 else 0.8
        elif regime == "breakout":
            for h in self.horizons:
                weights[h] = 1.2 if h <= 5 else 0.8
        elif regime == "chop":
            for h in self.horizons:
                weights[h] = 1.0

        long_score, short_score = 0.0, 0.0
        for h in self.horizons:
            p = horizon_probs.get(h, {1: 0.0, -1: 0.0})
            w = weights[h]
            long_score += w * p.get(1, 0.0)
            short_score += w * p.get(-1, 0.0)

        direction = "long" if long_score > short_score else "short"
        confidence = abs(long_score - short_score) / (sum(weights.values()) + 1e-12)
        agreement = 0
        for h in self.horizons:
            p = horizon_probs.get(h, {1: 0.0, -1: 0.0})
            d = "long" if p.get(1, 0.0) > p.get(-1, 0.0) else "short"
            if d == direction:
                agreement += 1
        return direction, confidence, agreement

