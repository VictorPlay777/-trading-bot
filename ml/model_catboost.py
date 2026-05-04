import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

try:
    from catboost import CatBoostClassifier
except Exception:  # pragma: no cover
    CatBoostClassifier = None


class DirectionModel:
    def __init__(self):
        if CatBoostClassifier is not None:
            self.model = CatBoostClassifier(
                depth=6,
                learning_rate=0.05,
                loss_function="MultiClass",
                verbose=False,
            )
            self.kind = "catboost"
        else:
            self.model = GradientBoostingClassifier(random_state=42)
            self.kind = "fallback_gbdt"
        self.columns = []

    def fit(self, X, y):
        self.columns = list(X.columns)
        self.model.fit(X.values, y)

    def predict_proba(self, row_dict):
        x = np.array([[row_dict.get(c, 0.0) for c in self.columns]])
        p = self.model.predict_proba(x)[0]
        classes = list(self.model.classes_)
        out = {int(classes[i]): float(p[i]) for i in range(len(classes))}
        return {1: out.get(1, 0.0), -1: out.get(-1, 0.0), 0: out.get(0, 0.0)}

