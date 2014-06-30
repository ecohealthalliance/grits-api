import argparse
import pickle
import numpy as np
from KeywordExtractor import *
import feature_extractors
from LocationExtractor import LocationExtractor
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline
import datetime

class Diagnoser():
    def __init__(self, classifier, dict_vectorizer,
                 keyword_links=None,
                 keyword_categories=None, cutoff_ratio=0.65):
        self.classifier = classifier
        self.keyword_categories = keyword_categories if keyword_categories else {}
        processing_pipeline = []
        if keyword_links:
            self.keyword_links = keyword_links
            processing_pipeline.append(('link', LinkedKeywordAdder(keyword_links)))
        processing_pipeline.append(('limit', LimitCounts(1)))
        self.keyword_processor = Pipeline(processing_pipeline)
        self.dict_vectorizer = dict_vectorizer
        self.keywords = dict_vectorizer.get_feature_names()
        self.keyword_extractor = KeywordExtractor(self.keywords)
        self.location_extractor = LocationExtractor()
        self.cutoff_ratio = cutoff_ratio
    def best_guess(self, X):
        probs = self.classifier.predict_proba(X)[0]
        p_max = max(probs)
        return [(i,p) for i,p in enumerate(probs) if p >= p_max * self.cutoff_ratio]
    def diagnose(self, content):
        base_keyword_dict = self.keyword_extractor.transform([content])[0]
        feature_dict = self.keyword_processor.transform([base_keyword_dict])
        X = self.dict_vectorizer.transform(feature_dict)[0]
        def diagnosis(i, p):
            scores = self.classifier.coef_[i] * X
            # Scores are normalized so they can be compared across different
            # classifications.
            norm = np.linalg.norm(scores)
            if norm > 0:
               scores /= norm
            scores *= p
            scored_keywords = zip(self.keywords, scores)
            return {
                'name' : self.classifier.classes_[i],
                'probability' : p,
                'keywords' : [{
                        'name' : kwd,
                        'score' : score,
                    }
                    for kwd, score in scored_keywords
                    if score > 0 and kwd in base_keyword_dict],
                'inferred_keywords' : [{
                        'name' : kwd,
                        'score' : score,
                    }
                    for kwd, score in scored_keywords
                    if score > 0 and kwd not in base_keyword_dict]
            }
        counts = list(feature_extractors.extract_counts(content))
        return {
            'diagnoserVersion' : '0.0.2',
            'dateOfDiagnosis' : datetime.datetime.now(),
            'keywords_found' : [
                {
                    'name' : keyword,
                    'count' : count,
                    'categories' : [cat 
                            for cat, kws in self.keyword_categories.items()
                            if keyword in kws]
                }
                for keyword, count in base_keyword_dict.items()
            ],
            'diseases': [diagnosis(i,p) for i,p in self.best_guess(X)],
            'features': list(feature_extractors.extract_dates(content)) +\
                counts + [
                {
                    'type' : 'cluster',
                    'centroid' : cluster['centroid'],
                    'locations' : cluster['locations'],
                }
                for cluster in self.location_extractor.transform([content])[0]
            ]
        }

if __name__ == '__main__':
    import Diagnoser
    parser = argparse.ArgumentParser()
    parser.add_argument('content', metavar='content', type=str, help='Text to diagnose')
    args = parser.parse_args()
    content = args.content
    with open('diagnoser.p', 'rb') as f:
        my_diagnoser = pickle.load(f)
        print my_diagnoser.diagnose(content)
