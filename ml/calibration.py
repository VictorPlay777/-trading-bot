import numpy as np
from sklearn.calibration import CalibratedClassifierCV


class ProbabilityCalibrator:
    def __init__(self, base_model):
        self.model = CalibratedClassifierCV(base_model, method="isotonic", cv=3)
        self.columns = []

    def fit(self, X, y):
        self.columns = list(X.columns)
        self.model.fit(X.values, y)

    def predict_proba(self, row):
        x = np.array([[row.get(c, 0.0) for c in self.columns]])
        p = self.model.predict_proba(x)[0]
        classes = list(self.model.classes_)
        m = {int(classes[i]): float(p[i]) for i in range(len(classes))}
        return {1: m.get(1, 0.0), -1: m.get(-1, 0.0), 0: m.get(0, 0.0)}

