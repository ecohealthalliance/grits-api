import argparse
import pickle
import numpy as np
from KeywordExtractor import *
from feature_extractors import extract_case_counts, extract_death_counts, extract_dates
from LocationExtractor import LocationExtractor
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline

class Diagnoser():
    def __init__(self, classifier, dict_vectorizer, keyword_links):
        self.classifier = classifier
        self.keyword_links = keyword_links
        self.keyword_processor = Pipeline([('addr', LinkedKeywordAdder(keyword_links)),
                                           ('limit', LimitCounts(1))])
        self.dict_vectorizer = dict_vectorizer
        self.keywords = dict_vectorizer.get_feature_names()
        self.keyword_extractor = KeywordExtractor(self.keywords)
        self.location_extractor = LocationExtractor()
    def best_guess(self, X, cutoff_ratio = 0.65):
        probs = self.classifier.predict_proba(X)[0]
        p_max = max(probs)
        return [(i,p) for i,p in enumerate(probs)if p >= p_max * cutoff_ratio]
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
                        'keyword' : kwd,
                        'score' : score,
                        'links' : self.keyword_links[kwd],
                    }
                    for kwd, score in scored_keywords
                    if score > 0 and kwd in base_keyword_dict],
                'inferred_keywords' : [{
                        'keyword' : kwd,
                        'score' : score,
                        'links' : self.keyword_links[kwd],
                    }
                    for kwd, score in scored_keywords
                    if score > 0 and kwd not in base_keyword_dict]
            }
        return {
            'keywords_found' : base_keyword_dict,
            'diseases': [diagnosis(i,p) for i,p in self.best_guess(X)],
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
