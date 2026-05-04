import numpy as np


class DriftMonitor:
    def __init__(self):
        self.baseline = {}

    def fit_baseline(self, feature_name: str, values):
        v = np.asarray(values, dtype=float)
        self.baseline[feature_name] = (float(np.nanmean(v)), float(np.nanstd(v) + 1e-12))

    def psi_like_score(self, feature_name: str, current_value: float) -> float:
        if feature_name not in self.baseline:
            return 0.0
        mu, sigma = self.baseline[feature_name]
        z = abs((current_value - mu) / sigma)
        return float(min(1.0, z / 5.0))

