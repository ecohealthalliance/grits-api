import celery
import json
import pickle
import diagnosis
import pymongo
from celery import Celery
import datetime
from distutils.version import StrictVersion

BROKER_URL = 'mongodb://localhost:27017/tasks'
celery_tasks = Celery('tasks', broker=BROKER_URL)
girder_db = pymongo.Connection('localhost')['girder']

def serialize_dates(obj):
    if isinstance(obj, dict):
        return { k: serialize_dates(v) for k, v in obj.items() }
    elif isinstance(obj, list):
        return map(serialize_dates, obj)
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    else:
        return obj

from diagnosis.Diagnoser import Diagnoser
with open('diagnoser.p', 'rb') as f:
    my_diagnoser = pickle.load(f)

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
    resource = girder_db.item.find_one(item_id)
    meta = resource['meta']
    rm_key(meta, 'diagnosing')
    
    prev_diagnosis = resource.get('meta').get('diagnosis')
    if prev_diagnosis and\
       StrictVersion(prev_diagnosis.diagnoserVersion) >=\
       StrictVersion(Diagnoser.__version__):
        girder_db.item.update({'_id': item_id}, resource)
        return resource
    translation = resource.get('private', {}).get('translation')
    if translation:
        clean_english_content = translation.get('english')
    else:
        clean_english_content = resource.get('private', {}).get('cleanContent')
    if clean_english_content:
        meta['diagnosis'] = my_diagnoser.diagnose(clean_english_content)
    else:
        meta['diagnosis'] = { 'error' : 'No content available to diagnose.' }
    girder_db.item.update({'_id': item_id}, resource)
    return resource

from corpora_shared.process_resources import extract_clean_content, attach_translations
from corpora_shared import translation
import corpora_shared.scrape as scraper
@celery_tasks.task
def process_girder_resource(item_id=None):
    """
    Scrape the meta.link of the girder item with the given id.
    Update the entry with the results, then update it with cleaned and 
    translated versions of the scraped content.
    """
    # The version of this function
    version = '0.0.1'
    resource = girder_db.item.find_one(item_id)
    private = resource['private'] = resource.get('private', {})
    private['processorVersion'] = version
    meta = resource['meta']
    rm_key(meta, 'processing')
    # Unset the diagnosis because the content might have changed.
    rm_key(meta, 'diagnosis')
    
    prev_scraped_data = private.get('scrapedData')
    if not prev_scraped_data or\
       StrictVersion(prev_scraped_data['scraperVersion']) <\
       StrictVersion(scraper.__version__):
        private['scrapedData'] = scraper.scrape(resource['meta']['link'])
    if private['scrapedData'].get('unscrapable'):
        return resource
    
    content = private['scrapedData']['content']
    clean_content = extract_clean_content(content)
    if not clean_content:
        meta['error'] = "Could not clean content."
        girder_db.item.update({'_id': item_id}, resource)
        return resource
    private['cleanContent'] = clean_content
    
    if not translation.is_english(clean_content):
        prev_translation = resource.get('private', {}).get('translation')
        if not prev_translation:
            clean_content_en = translation.get_translation(str(item_id))
            if clean_content_en:
                private['translation'] = {
                    'english' : clean_content_en,
                    'translationDate' : datetime.datetime.now(),
                    'translationService' : 'stored corpora translation'
                }
            else:
                from mstranslate import MSTranslate
                try:
                    # TODO: This should be an EHA account
                    translation_api = MSTranslate('grits_api', 't75FbdCCeHfdUufng27hFbtEzSmxQMbaUr7M3jq/0VY=')
                    private['translation'] = {
                        'english' : translation_api.translate(clean_content, 'en'),
                        'translationDate' : datetime.datetime.now(),
                        'translationService' : 'microsoft'
                    }
                except:
                    private['translation'] = {
                        'error' : 'Exception during translation.'
                    }
    girder_db.item.update({'_id': item_id}, resource)
    return resource
