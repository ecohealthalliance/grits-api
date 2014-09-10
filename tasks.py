import celery
import json
import bson
import pickle
import diagnosis
import pymongo
from celery import Celery
import datetime
from distutils.version import StrictVersion
import config
import microsofttranslator
import logging
import datetime
def make_json_compat(obj):
    """
    Coerce the types in an object to values that can be jsonified.
    """
    base_types = [str, unicode, basestring, bool, int, long, float, type(None)]
    if type(obj) in base_types:
        return obj
    elif isinstance(obj, list):
        return map(make_json_compat, obj)
    elif isinstance(obj, dict):
        return { k : make_json_compat(v) for k,v in obj.items() }
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, bson.ObjectId):
        return str(obj)
    else:
        raise TypeError(type(obj))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

celery_tasks = Celery('tasks', broker=config.BROKER_URL)

celery_tasks.conf.update(
    CELERY_TASK_SERIALIZER='json',
    CELERY_ACCEPT_CONTENT=['json'],  # Ignore other content
    CELERY_RESULT_SERIALIZER='json',
    CELERY_RESULT_BACKEND = config.BROKER_URL,
    CELERY_MONGODB_BACKEND_SETTINGS = {
        'database': 'tasks',
        'taskmeta_collection': 'taskmeta',
    }
)

db_handle = pymongo.Connection(config.mongo_url)
girder_db = db_handle['girder']

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

def rm_key(d, key):
    if key in d:
        d.pop(key)
    return d

@celery_tasks.task
def diagnose_girder_resource(prev_result=None, item_id=None):
    """
    Run the diagnostic classifiers/feature extractors
    on the girder item with the given id.
    """
    item_id = bson.ObjectId(item_id)
    resource = girder_db.item.find_one(item_id)
    meta = resource['meta']
    rm_key(meta, 'diagnosing')
    
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

from corpora.process_resources import extract_clean_content, attach_translations
from corpora import translation as translation_lib
import corpora.scrape as scraper
consecutive_exceptions = 0
processor_version = '0.0.2'
@celery_tasks.task
def process_girder_resource(item_id=None):
    """
    Scrape the meta.link of the girder item with the given id.
    Update the entry with the results, then update it with cleaned and 
    translated versions of the scraped content.
    """
    logger.info('Processing girder resource:' + item_id)
    item_id = bson.ObjectId(item_id)
    global processor_version
    resource = girder_db.item.find_one(item_id)
    private = resource['private'] = resource.get('private', {})
    private['processorVersion'] = processor_version
    meta = resource['meta']
    rm_key(meta, 'processing')
    # Unset the diagnosis because the content might have changed.
    rm_key(meta, 'diagnosis')
    
    prev_scraped_data = private.get('scrapedData')
    if not prev_scraped_data or\
       StrictVersion(prev_scraped_data['scraperVersion']) <\
       StrictVersion(scraper.__version__):
        logger.info('Scraping:' + resource['meta']['link'])
        private['scrapedData'] = scraper.scrape(resource['meta']['link'])
    if private['scrapedData'].get('unscrapable'):
        girder_db.item.update({'_id': item_id}, resource)
        return make_json_compat(resource)
    
    content = private['scrapedData']['content']
    clean_content = extract_clean_content(content)
    prev_clean_content = private.get('cleanContent', {}).get('content')
    if not clean_content:
        private['cleanContent'] = { "error" : "Could not clean content." }
        girder_db.item.update({'_id': item_id}, resource)
        return make_json_compat(resource)
    private['cleanContent'] = { 'content' : clean_content }
    
    if not translation_lib.is_english(clean_content):
        prev_translation = resource.get('private', {}).get('englishTranslation')
        if not prev_translation or prev_clean_content != clean_content:
            # The stored translation code can be removed eventually
            # We have some tranlations for specific documents saved in json files.
            # Once they are in the database there is no reason to keep those files
            # or this code.
            stored_translation = translation_lib.get_translation(str(item_id))
            if stored_translation:
                private['englishTranslation'] = {
                    'content' : stored_translation,
                    'translationDate' : datetime.datetime.now(),
                    'translationService' : 'stored translation'
                }
            else:
                global consecutive_exceptions
                if consecutive_exceptions > 4:
                    # Back off when we reach more than 4 consecutive exceptions
                    # because we probably hit the api limit.
                    private['englishTranslation'] = {
                        'error' : 'Too many consecutive exceptions'
                    }
                else:
                    try:
                        translation_api = microsofttranslator.Translator(config.bing_translate_id, config.bing_translate_secret)
                        translation = translation_api.translate(clean_content, 'en')
                        if translation.startswith("TranslateApiException:"):
                            raise microsofttranslator.TranslateApiException(translation.split("TranslateApiException:")[1]) 
                        private['englishTranslation'] = {
                            'content' : translation,
                            'translationDate' : datetime.datetime.now(),
                            'translationService' : 'microsoft'
                        }
                        logger.info('Translated: ' + resource['meta']['link'])
                        consecutive_exceptions = 0
                    except microsofttranslator.TranslateApiException as e:
                        consecutive_exceptions += 1
                        private['englishTranslation'] = {
                            'error' : 'Exception during translation.'
                        }
    girder_db.item.update({'_id': item_id}, resource)
    return make_json_compat(resource)

@celery_tasks.task
def scrape(url):
    """
    Scrape the meta.link of the girder item with the given id.
    Update the entry with the results, then update it with cleaned and 
    translated versions of the scraped content.
    """
    return make_json_compat(scraper.scrape(url))

@celery_tasks.task
def process_text(text_obj):
    if text_obj.get('unscrapable'):
        return text_obj
    content = text_obj['content']
    clean_content = extract_clean_content(content)
    if not clean_content:
        text_obj['cleanContent'] = { 'error' : "Could not clean content." }
    else:
        text_obj['cleanContent'] = { 'content' : clean_content }
    # TODO: Add translation
    return text_obj

@celery_tasks.task
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
