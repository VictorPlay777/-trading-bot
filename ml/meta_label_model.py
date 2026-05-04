from sklearn.ensemble import RandomForestClassifier
import numpy as np


class MetaLabelModel:
    def __init__(self):
        self.model = RandomForestClassifier(
            n_estimators=120,
            max_depth=6,
            min_samples_leaf=10,
            random_state=42,
        )
        self.columns = []
        self.ready = False

    def fit(self, X, y):
        self.columns = list(X.columns)
        self.model.fit(X.values, y)
        self.ready = True

    def approve(self, row: dict) -> float:
        if not self.ready:
            return 0.5
        x = np.array([[row.get(c, 0.0) for c in self.columns]])
        return float(self.model.predict_proba(x)[0][1])

