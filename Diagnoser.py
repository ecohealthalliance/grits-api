import argparse
import pickle
import numpy as np
from KeywordExtractor import KeywordExtractor
from feature_extractors import extract_case_counts, extract_death_counts, extract_dates

class Diagnoser():
    def __init__(self, classifier="classifier.p", keywords="found_keywords.p"):
        self.classifier = pickle.load(open(classifier, "rb"))
        self.keywords = pickle.load(open(keywords, "rb"))
        self.extract_features = KeywordExtractor([k.strip() for k in self.keywords]).extract_features
        
    def diagnose(self, content):
        feature_dict = self.extract_features(content)
        X = np.array([feature_dict.get(f, 0) for f in self.keywords])
        CUTOFF_RATIO = 1.0 / 1.5
        probs = self.classifier.predict_proba(X)[0]
        p_max = max(probs)
        diseases = [{
            'name' : self.classifier.classes_[i],
            'probability' : p,
            'keywords' : [[kwd, co] for co, kwd in zip(self.classifier.coef_[i] * X, self.keywords)
                                    if co > 0]
        } for i, p in enumerate(probs)
          if p >= p_max * CUTOFF_RATIO]
        return {
            'diseases': diseases,
            'features': [
                {
                    'type' : 'datetime',
                    'value' : d,
                } for d in extract_dates(content)
            ] + [
                {
                    'type' : 'caseCount',
                    'value' : count,
                } for count in extract_case_counts(content)
            ] + [
                {
                    'type' : 'deathCount',
                    'value' : count,
                } for count in extract_death_counts(content)
            ]
        }

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('content', metavar='content', type=str, help='Text to diagnose')
    args = parser.parse_args()
    content = args.content
    print Diagnoser().diagnose(content)
