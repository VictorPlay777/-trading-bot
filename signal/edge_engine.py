class EdgeEngine:
    @staticmethod
    def clipped_probs(p):
        return {
            1: min(0.95, max(0.05, p.get(1, 0.0))),
            -1: min(0.95, max(0.05, p.get(-1, 0.0))),
            0: min(0.95, max(0.05, p.get(0, 0.0))),
        }

    def compute(self, probs):
        p = self.clipped_probs(probs)
        if p[1] > p[-1]:
            return "long", p[1], abs(p[1] - p[-1])
        return "short", p[-1], abs(p[1] - p[-1])

