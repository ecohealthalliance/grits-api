import argparse
import pickle
import numpy as np
from KeywordExtractor import *
from feature_extractors import extract_case_counts, extract_death_counts, extract_dates
from LocationExtractor import LocationExtractor
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline

class Diagnoser():
    def __init__(self, classifier, dict_vectorizer,
                 keyword_links=None,
                 keyword_categories=None, cutoff_ratio=0.7):
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
            scored_keywords = zip(self.keywords, self.classifier.coef_[i] * X)
            return {
                'name' : self.classifier.classes_[i],
                'probability' : p,
                'keywords' : [{
                        'name' : kwd,
                        'score' : score,
                        'categories' : [cat
                            for cat, kws in self.keyword_categories.items()
                            if kwd in kws]
                    }
                    for kwd, score in scored_keywords
                    if score > 0 and kwd in base_keyword_dict],
                'inferred_keywords' : [{
                        'name' : kwd,
                        'score' : score,
                        'categories' : [cat 
                            for cat, kws in self.keyword_categories.items()
                            if kwd in kws]
                    }
                    for kwd, score in scored_keywords
                    if score > 0 and kwd not in base_keyword_dict]
            }
        return {
            'keywords_found' : base_keyword_dict,
            'diseases': [diagnosis(i,p) for i,p in self.best_guess(X)],
            'features': [
                d for d in extract_dates(content)
            ] + [
                count_object for count_object in extract_case_counts(content)
            ] + [
                count_object for count_object in extract_death_counts(content)
            ] + [
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
