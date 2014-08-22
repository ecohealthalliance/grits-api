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
from annotator.patient_info_annotator import PatientInfoAnnotator
from annotator.jvm_nlp_annotator import JVMNLPAnnotator

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def time_sofar_gen(start_time):
    """
    A generator that returns the time elapsed since the passed in start_time.
    """
    while True:
        yield '[' + str(datetime.datetime.now() - start_time) + ']'

import yaml, os
curdir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(curdir, "../diseaseToParent.yaml")) as f:
    disease_to_parent = yaml.load(f)

class Diagnoser():

    __version__ = '0.1.1'

    def __init__(
        self, classifier, dict_vectorizer,
        cutoff_ratio=0.65,
        keyword_array=None
    ):
        self.keyword_array = keyword_array
        self.classifier = classifier
        self.geoname_annotator = GeonameAnnotator()
        self.case_count_annotator = CaseCountAnnotator()
        self.patient_info_annotator = PatientInfoAnnotator()
        self.jvm_nlp_annotator = JVMNLPAnnotator(['times'])
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
        result = set()
        for i,p in enumerate(probs):
            cutoff_ratio = self.cutoff_ratio
            parent = disease_to_parent.get(self.classifier.classes_[i])
            parents = []
            if parent:
                parents.append(parent)
                while parents[-1] in disease_to_parent:
                    parents.append(disease_to_parent[parents[-1]])
            if p >= p_max * self.cutoff_ratio:
                result.add((i,p))
                for i2, label in enumerate(self.classifier.classes_.tolist()):
                    if label in parents:
                        result.add((i2,max(p, probs[i2])))
        return list(result)
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

        anno_doc = AnnoDoc(content)

        anno_doc.add_tier(self.geoname_annotator)
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
                geonames_grouped[
                    span.geoname['geonameid']
                ]['textOffsets'].append(
                    [span.start, span.end]
                )
        logger.info(time_sofar.next() + 'Annotated geonames')

        anno_doc.add_tier(self.case_count_annotator)
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

        anno_doc.add_tier(self.jvm_nlp_annotator)
        times_grouped = {}
        for span in anno_doc.tiers['times'].spans:
            # TODO -- how should we handle DURATION and other exotice date types?
            if span.type == 'DATE':
                if not span.label in times_grouped:
                    times_grouped[span.label] = {
                        'type': 'datetime',
                        'name': span.label,
                        'value': span.label,
                        'textOffsets': [
                            [span.start, span.end]
                        ]
                    }
                else:
                    times_grouped[span.label]['textOffsets'].append(
                        [span.start, span.end]
                    )
        logger.info(time_sofar.next() + 'Annotated times')

        logger.info(time_sofar.next() + 'Extracted dates')

        anno_doc.add_tier(self.patient_info_annotator, keyword_categories={
            # TODO: Use keywords
            'occupation' : ['farmer'],
        })
        keypoints = []
        for span in anno_doc.tiers['patientInfo'].spans:
            keypoints.append(
                dict(
                    span.metadata,
                    type='patientInfo',
                    textOffsets=[[span.start, span.end]]
                )
            )
        logger.info(time_sofar.next() + 'Extracted patient info')

        return {
            'diagnoserVersion' : self.__version__,
            'dateOfDiagnosis' : datetime.datetime.now(),
            'keywords_found' : [
                {
                    'name' : unicode(keyword),
                    'count' : int(count),
                    'categories' : [
                        kw['category']
                        for kw in self.keyword_array
                        if kw['keyword'].lower() == keyword.lower()
                    ]
                }
                for keyword, count in base_keyword_dict.items()
            ],
            'diseases': diseases,
            'keypoints' : keypoints,
            'features': (
                case_counts +
                times_grouped.values() + 
                geonames_grouped.values()
            )
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
