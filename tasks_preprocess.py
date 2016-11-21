# This file is separate from tasks.py so that it can function without loading
# the classifier data pickles. This makes it possible to preprocess articles
# without training a classifier, and it reduces the memory footprint.
import celery
import json
import bson
from pymongo import MongoClient
from celery import Celery
import datetime
from distutils.version import StrictVersion
import config
import logging
import datetime
from scraper.process_resources import extract_clean_content
from scraper import scraper
from scraper.translation import Translator

my_translator = Translator(config)

processor_version = '0.1.0'

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
    elif isinstance(obj, bson.int64.Int64):
        return int(obj)
    else:
        raise TypeError(type(obj))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

celery_tasks = Celery('tasks', broker=config.BROKER_URL)

celery_tasks.conf.update(
    CELERY_TASK_SERIALIZER='json',
    CELERY_ACCEPT_CONTENT=['json'],  # Ignore other content
    CELERY_RESULT_SERIALIZER='json',
    CELERY_RESULT_BACKEND = config.BROKER_URL
)

celery_tasks.conf.broker_transport_options = {'visibility_timeout': 3600}  # 1 hour.
#Option below to store results of tasks in redis as well
#celery_tasks.conf.result_backend = config.BROKER_URL

db_handle = MongoClient(config.mongo_url)
girder_db = db_handle['girder']

@celery_tasks.task(name='tasks.process_girder_resource')
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
    
    meta = resource['meta']
    
    if StrictVersion(private.get('processorVersion', '0.0.0')) >=\
       StrictVersion(processor_version):
        # Don't reprocess the article if the processor hasn't changed,
        # unless there was an error during translation.
        if private.get('englishTranslation', {}).get('error'):
            pass
        else:
            girder_db.item.update({'_id': item_id}, resource)
            return make_json_compat(resource)
    
    private['processorVersion'] = processor_version

    # Remove any existing diagnosis because the content might have changed.
    if 'diagnosis' in  meta:
        del meta['diagnosis']
    
    prev_scraped_data = private.get('scrapedData')
    if not prev_scraped_data or\
       StrictVersion(prev_scraped_data['scraperVersion']) <\
       StrictVersion(scraper.__version__):
        logger.info('Scraping url: ' + resource['meta']['link'])
        private['scrapedData'] = scraper.scrape(resource['meta']['link'])
    if private['scrapedData'].get('unscrapable'):
        girder_db.item.update({'_id': item_id}, resource)
        return make_json_compat(resource)
    try:
        content = private['scrapedData']['htmlContent']
    except KeyError as e:
        print resource
        raise e
    clean_content_obj = extract_clean_content(content)
    prev_clean_content_obj = private.get('cleanContent')
    # In some db items cleanContent is a string.
    if isinstance(prev_clean_content_obj, dict):
        prev_clean_content = prev_clean_content_obj.get('content')
    else:
        prev_clean_content = None
    private['cleanContent'] = clean_content_obj
    if clean_content_obj.get('malformed'):
        girder_db.item.update({'_id': item_id}, resource)
        return make_json_compat(resource)
    
    if not my_translator.is_english(clean_content_obj['content']):
        prev_translation = resource.get('private', {}).get('englishTranslation')
        if( not prev_translation or
            prev_clean_content != clean_content_obj['content'] or
            prev_translation.get('error')):
            private['englishTranslation'] =\
                my_translator.translate_to_english(
                    clean_content_obj['content'])
            logger.info('Article translated: ' + resource['meta']['link'])
            if private['englishTranslation'].get('error'):
                logger.warn('Translation Error: ' + private['englishTranslation'].get('error'))
    girder_db.item.update({'_id': item_id}, resource)
    return make_json_compat(resource)

@celery_tasks.task(name='tasks.scrape')
def scrape(url):
    """
    Scrape the meta.link of the girder item with the given id.
    Update the entry with the results, then update it with cleaned and 
    translated versions of the scraped content.
    """
    return make_json_compat(scraper.scrape(url))

@celery_tasks.task(name='tasks.process_text')
def process_text(text_obj):
    result = {}
    # These first conditions are for handling scraper output. They are currently
    # unnecessairy since we don't allow users to submit URLs.
    if text_obj.get('unscrapable'):
        result['scrapedData'] = text_obj
        result['error'] = result['scrapedData']['error']
        return make_json_compat(result)
    if 'htmlContent' in text_obj:
        result['scrapedData'] = text_obj
        clean_content = extract_clean_content(text_obj['htmlContent'])
    else:
        clean_content = text_obj
    if my_translator.is_english(clean_content['content']):
        result['cleanContent'] = clean_content
    else:
        result['englishTranslation'] = my_translator.translate_to_english(
            clean_content['content'])
        result['cleanContent'] = clean_content
    return make_json_compat(result)
