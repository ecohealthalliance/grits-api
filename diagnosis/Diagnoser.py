import argparse
import pickle
import numpy as np
from KeywordExtractor import *
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline
import datetime
from annotator.annotator import AnnoDoc
from annotator.geoname_annotator import GeonameAnnotator
from annotator.count_annotator import CountAnnotator
from annotator.patient_info_annotator import PatientInfoAnnotator
from annotator.jvm_nlp_annotator import JVMNLPAnnotator
import disease_label_table
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

    __version__ = '0.1.4'

    def __init__(
        self, classifier, dict_vectorizer,
        cutoff_ratio=0.65,
        keyword_array=None
    ):
        self.keyword_array = keyword_array
        self.classifier = classifier
        self.geoname_annotator = GeonameAnnotator()
        self.count_annotator = CountAnnotator()
        # TODO: Rename patient info annotator
        self.keypoint_annotator = PatientInfoAnnotator()
        self.jvm_nlp_annotator = JVMNLPAnnotator(['times'])
        self.keyword_annotator = KeywordAnnotator()
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
    def diagnose(self, content, diseases_only=False):
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
        if diseases_only:
            return {
                'diseases': diseases
            }
        logger.info(time_sofar.next() + 'Diagnosed diseases')

        anno_doc = AnnoDoc(content)
        anno_doc.add_tier(self.keyword_annotator)
        logger.info('keywords annotated')
        try:
            anno_doc.add_tier(self.jvm_nlp_annotator)
        except Exception as e:
            logger.error(
                time_sofar.next() +
                'Could not annotate times, ' +
                'the JVM time extraction server might not be running.' +
                '\nException:\n' + str(e)
            )
        logger.info('times annotated')
        anno_doc.add_tier(self.count_annotator)
        logger.info('counts annotated')
        anno_doc.add_tier(self.geoname_annotator)
        logger.info('geonames annotated')
        anno_doc.filter_overlapping_spans(
            tier_names=[ 'times', 'geonames', 'diseases', 'hosts', 'modes',
                         'pathogens', 'symptoms' ]
        )

        logger.info('filtering overlapping spans done')

        times_grouped = {}
        if 'times' in anno_doc.tiers:
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

        counts = []
        for span in anno_doc.tiers['counts'].spans:
            count_dict = span.to_dict()
            count_dict['type'] = 'count'
            counts.append(count_dict)
            # Include legacy case counts so the diagnositic dashboard
            # doesn't break.
            if "case" in count_dict['attributes']:
                counts.append({
                    'type': "caseCount",
                    'text': count_dict['text'],
                    'value': count_dict['label'],
                    'modifiers': count_dict['attributes'],
                    'cumulative': "cumulative" in count_dict['attributes'],
                    'textOffsets': count_dict['textOffsets']
                })
        anno_doc.add_tier(self.keypoint_annotator, keyword_categories={
            'location' : anno_doc.tiers['geonames'].spans,
            'time' : anno_doc.tiers['times'].spans if 'times' in anno_doc.tiers else [],
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
        return {
            'diagnoserVersion': self.__version__,
            'dateOfDiagnosis': datetime.datetime.now(),
            'diseases': diseases,
            'keypoints': keypoints,
            'features': counts +\
                        geonames_grouped.values() +\
                        times_grouped.values() +\
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
