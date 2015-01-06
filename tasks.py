import celery
import json
import bson
import pickle
import diagnosis
import pymongo
import datetime
from distutils.version import StrictVersion
import datetime

import tasks_preprocess
from tasks_preprocess import girder_db
from tasks_preprocess import celery_tasks
from tasks_preprocess import make_json_compat

from diagnosis.Diagnoser import Diagnoser
with open('classifier.p') as f:
    my_classifier = pickle.load(f)
with open('dict_vectorizer.p') as f:
    my_dict_vectorizer = pickle.load(f)
with open('keyword_array.p') as f:
    keyword_array = pickle.load(f)
my_diagnoser = Diagnoser(
    my_classifier,
    my_dict_vectorizer,
    keyword_array=keyword_array,
    cutoff_ratio=.7
)

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@celery_tasks.task(name='tasks.diagnose_girder_resource')
def diagnose_girder_resource(prev_result=None, item_id=None):
    """
    Run the diagnostic classifiers/feature extractors
    on the girder item with the given id.
    """
    logger.info("Diagnosing article with girder id: " + item_id)
    if prev_result == None:
        logger.error('Processing might have failed.')
    item_id = bson.ObjectId(item_id)
    resource = girder_db.item.find_one(item_id)
    meta = resource['meta']
    
    prev_diagnosis = resource.get('meta').get('diagnosis')
    if prev_diagnosis and\
       StrictVersion(prev_diagnosis.get('diagnoserVersion', '0.0.0')) >=\
       StrictVersion(Diagnoser.__version__):
        girder_db.item.update({'_id': item_id}, resource)
        return make_json_compat(resource)
    english_translation = resource\
        .get('private', {})\
        .get('englishTranslation', {})\
        .get('content')
    if english_translation:
        clean_english_content = english_translation
    else:
        clean_english_content = resource\
            .get('private', {})\
            .get('cleanContent', {})\
            .get('content')
    if clean_english_content:
        logger.info('Diagnosing text:\n' + clean_english_content)
        meta['diagnosis'] = my_diagnoser.diagnose(clean_english_content)
    else:
        meta['diagnosis'] = { 'error' : 'No content available to diagnose.' }
    girder_db.item.update({'_id': item_id}, resource)
    # Log the item so we have a record of the diagnosis and the data it relates
    # to in case we ever need to refer back to it (e.g. notifying users that
    # the diagnosis of an article they reviewed changed because of an update):
    logged_resource = {}
    for k, v in resource.items():
        if k == '_id':
            logged_resource['itemId'] = v
        else:
            logged_resource[k] = v
    girder_db['diagnosisLog'].insert(logged_resource)
    return make_json_compat(resource)

@celery_tasks.task(name='tasks.diagnose')
def diagnose(text_obj):
    english_translation = text_obj.get('englishTranslation', {}).get('content')
    if english_translation:
        clean_english_content = english_translation
    else:
        clean_english_content = text_obj.get('cleanContent', {}).get('content')
    if clean_english_content:
        logger.info('Diagnosing text:\n' + clean_english_content)
        return make_json_compat(my_diagnoser.diagnose(clean_english_content))
    else:
        return { 'error' : 'No content available to diagnose.' }
