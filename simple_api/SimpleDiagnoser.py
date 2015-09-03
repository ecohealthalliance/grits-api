import numpy as np
from KeywordExtractor import *
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline

import disease_label_table

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import datetime

def time_sofar_gen(start_time):
    """
    A generator that returns the time elapsed since the passed in start_time.
    """
    while True:
        yield '[' + str(datetime.datetime.now() - start_time) + ']'

class SimpleDiagnoser(object):
    def __init__(
        self,
        classifier,
        dict_vectorizer,
        cutoff_ratio=0.7,
        keyword_array=None
    ):
        self.keyword_array = keyword_array
        self.classifier = classifier
        processing_pipeline = []
        processing_pipeline.append(('link', LinkedKeywordAdder(keyword_array)))
        processing_pipeline.append(('limit', LimitCounts(1)))
        self.keyword_processor = Pipeline(processing_pipeline)
        self.dict_vectorizer = dict_vectorizer
        self.keywords = dict_vectorizer.get_feature_names()
        self.keyword_extractor = KeywordExtractor(keyword_array)
        self.cutoff_ratio = cutoff_ratio
    def best_guess(self, X):
        probs = self.classifier.predict_proba(X)[0]
        p_max = max(probs)
        result = {}
        for i,p in enumerate(probs):
            cutoff_ratio = self.cutoff_ratio
            parents = disease_label_table.get_inferred_labels(self.classifier.classes_[i])
            if p >= p_max * self.cutoff_ratio:
                result[i] = max(p, result.get(i, 0))
                for i2, label in enumerate(self.classifier.classes_):
                    if label in parents:
                        result[i2] = max(p, probs[i2], result.get(i2, 0))
        return result.items()
    def diagnose(self, content):
        time_sofar = time_sofar_gen(datetime.datetime.now())
        base_keyword_dict = self.keyword_extractor.transform([content])[0]
        feature_dict = self.keyword_processor.transform([base_keyword_dict])
        X = self.dict_vectorizer.transform(feature_dict)[0]

        logger.info(time_sofar.next() + 'Computed feature vector')
        def diagnosis(i, p):
            scores = self.classifier.coef_[i] * X
            # Scores are normalized so they can be compared across different
            # classifications.
            norm = np.linalg.norm(scores)
            if norm > 0:
               scores /= norm
            scores *= p
            # These might be numpy types. I coerce them to native python
            # types so we can easily serialize the output as json.

            scored_keywords = zip(self.keywords, scores)
            keyword_scores = {}
            for keyword, score in scored_keywords:
                if score > 0 and keyword in base_keyword_dict:
                    keyword_scores[keyword] = float(score)

            return {
                'name' : unicode(self.classifier.classes_[i]),
                'probability' : float(p),
                'keywords' : [{
                        'name' : unicode(kwd),
                        'score' : float(score),
                    }
                    for kwd, score in scored_keywords
                    if score > 0 and kwd in base_keyword_dict],
                'inferred_keywords' : [{
                        'name' : unicode(kwd),
                        'score' : float(score),
                    }
                    for kwd, score in scored_keywords
                    if score > 0 and kwd not in base_keyword_dict]
            }
        diseases = [diagnosis(i,p) for i,p in self.best_guess(X)]
        logger.info(time_sofar.next() + 'Diagnosed diseases')
        
        return {
            'dateOfDiagnosis' : datetime.datetime.now(),
            'diseases': diseases
        }
