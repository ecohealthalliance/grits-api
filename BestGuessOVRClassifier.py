from sklearn.multiclass import OneVsRestClassifier

class BestGuessOVRClassifier(OneVsRestClassifier):
    """
    This OVR classifier will always choose at least one label,
    regardless of the probability
    """
    CUTOFF_RATIO = 1.0 / 1.5
    def predict(self, X):
        probs = self.predict_proba(X)[0]
        p_max = max(probs)
        return [tuple([self.classes_[i] for i, p in enumerate(probs) if p >= p_max * self.CUTOFF_RATIO ])]