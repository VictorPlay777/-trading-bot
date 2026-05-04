import os, joblib, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV

class ProbModel:
    def __init__(self):
        self.scaler = StandardScaler(with_mean=False)
        # Base model
        base_model = LogisticRegression(
            C=0.1,
            solver='sag',
            max_iter=5000,
            random_state=42
        )
        # Calibrated model for better probability estimates
        self.model = CalibratedClassifierCV(
            base_model,
            method='isotonic',
            cv=3
        )
        self.classes_ = np.array([-1, 0, 1])
    
    def fit_partial(self, X, y):
        # Train from scratch each time (not incremental) to avoid overfitting
        Xs = self.scaler.fit_transform(X)
        self.model.fit(Xs, y)
        return self
    
    def predict_proba_row(self, x_row):
        Xs = self.scaler.transform(x_row.reshape(1, -1))
        p = self.model.predict_proba(Xs)[0]
        return {int(self.model.classes_[i]): float(p[i]) for i in range(len(self.model.classes_))}
    
    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump({'scaler': self.scaler, 'model': self.model}, path)
    
    def load(self, path):
        obj = joblib.load(path)
        self.scaler = obj['scaler']
        self.model = obj['model']
        self.classes_ = getattr(self.model, 'classes_', self.classes_)
        return self
