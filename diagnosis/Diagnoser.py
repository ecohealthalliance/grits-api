import argparse
import pickle
import numpy as np
from KeywordExtractor import *
import feature_extractors
from LocationExtractor import LocationExtractor
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline
import datetime
from annotator.annotator import AnnoDoc
from annotator.geoname_annotator import GeonameAnnotator
from annotator.case_count_annotator import CaseCountAnnotator
from annotator.keyword_annotator import KeywordAnnotator

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def time_sofar_gen(start_time):
    """
    A generator that returns the time elapsed since the passed in start_time.
    """
    while True:
        yield '[' + str(datetime.datetime.now() - start_time) + ']'

class Diagnoser():

    __version__ = '0.0.1'

    def __init__(self, classifier, dict_vectorizer,
                 keyword_links=None,
                 keyword_categories=None, cutoff_ratio=0.65):
        self.classifier = classifier
        self.geoname_annotator = GeonameAnnotator()
        self.case_count_annotator = CaseCountAnnotator()
        self.keyword_annotator = KeywordAnnotator()
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
        self.cutoff_ratio = cutoff_ratio
    def best_guess(self, X):
        probs = self.classifier.predict_proba(X)[0]
        p_max = max(probs)
        return [(i,p) for i,p in enumerate(probs) if p >= p_max * self.cutoff_ratio]
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

            scored_keywords = zip(self.keywords, scores)
            keyword_scores = {}
            for keyword, score in scored_keywords:
                if score > 0 and keyword in base_keyword_dict:
                    keyword_scores[keyword] = float(score)

            return {
                'name' : self.classifier.classes_[i],
                'probability' : p,
                'scored_keywords': scored_keywords,
                'inferred_keywords' : [{
                        'name' : kwd,
                        'score' : score,
                    }
                    for kwd, score in scored_keywords
                    if score > 0 and kwd not in base_keyword_dict]
            }
        diseases = [diagnosis(i,p) for i,p in self.best_guess(X)]
        logger.info(time_sofar.next() + 'Diagnosed diseases')

        anno_doc = AnnoDoc(content)
        anno_doc.add_tier(self.keyword_annotator)
        anno_doc.add_tier(self.case_count_annotator)
        anno_doc.add_tier(self.geoname_annotator)
        anno_doc.filter_overlapping_spans(
            tier_names=[ 'locations', 'diseases', 'hosts', 'modes', 'pathogens', 'symptoms' ])

        geonames_grouped = {}
        for span in anno_doc.tiers['geonames'].spans:
            if not span.geoname['geonameid'] in geonames_grouped:
                geonames_grouped[span.geoname['geonameid']] = {
                    'type': 'location',
                    'name': span.label,
                    'geoname': span.geoname,
                    'textOffsets': [
                        [span.start, span.end]
                    ]
                }
            else:
                geonames_grouped[span.geoname['geonameid']]['textOffsets'].append(
                    [span.start, span.end]
                )
        logger.info(time_sofar.next() + 'Annotated geonames')

        case_counts = []
        for span in anno_doc.tiers['caseCounts'].spans:
            case_counts.append({
                'type': span.type,
                'text': span.text,
                'value': span.label,
                'modifiers': span.modifiers,
                'cumulative': span.cumulative,
                'textOffsets': [[span.start, span.end]]
                })
        logger.info(time_sofar.next() + 'Extracted case counts')

        keyword_types = ['diseases', 'hosts', 'modes', 'pathogens', 'symptoms']
        keyword_groups = {}
        for keyword_type in keyword_types:
            keyword_groups[keyword_type] = {}
            for span in anno_doc.tiers[keyword_type].spans:
                if not span.label in keyword_groups[keyword_type]:
                    keyword_groups[keyword_type][span.label] = {
                        'type': keyword_type,
                        'value': span.label,
                        'textOffsets': [[span.start, span.end]]
                    }
                else:
                    keyword_groups[keyword_type][span.label]['textOffsets'].append(
                        [span.start, span.end]
                    )

        extracted_dates = list(feature_extractors.extract_dates(content))
        logger.info(time_sofar.next() + 'Extracted dates')

        return {
            'diagnoserVersion' : self.__version__,
            'dateOfDiagnosis' : datetime.datetime.now(),
            'diseases': diseases,
            'features': extracted_dates +\
                        case_counts +\
                        geonames_grouped.values() +\
                        keyword_groups['diseases'].values() +\
                        keyword_groups['hosts'].values() +\
                        keyword_groups['modes'].values() +\
                        keyword_groups['pathogens'].values() +\
                        keyword_groups['symptoms'].values()
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
