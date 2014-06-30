import celery
import json
import pickle
import diagnosis
import pymongo
from celery import Celery
import datetime
from distutils.version import StrictVersion
import config

celery_tasks = Celery('tasks', broker=config.BROKER_URL)
celery_tasks.conf.update(
    CELERY_TASK_SERIALIZER='json',
    CELERY_ACCEPT_CONTENT=['json'],  # Ignore other content
    CELERY_RESULT_SERIALIZER='json'
)

db_handle = pymongo.Connection(config.mongo_url)
girder_db = db_handle['girder']

from diagnosis.Diagnoser import Diagnoser
with open('classifier.p') as f:
    my_classifier = pickle.load(f)
with open('dict_vectorizer.p') as f:
    my_dict_vectorizer = pickle.load(f)
with open('keyword_links.p') as f:
    keyword_links = pickle.load(f)
with open('keyword_sets.p') as f:
    keyword_sets = pickle.load(f)
my_diagnoser = Diagnoser(my_classifier,
                         my_dict_vectorizer,
                         keyword_links=keyword_links,
                         keyword_categories=keyword_sets,
                         cutoff_ratio=.7)

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
        return# resource
    translation = resource.get('private', {}).get('translation')
    if translation:
        clean_english_content = translation.get('english')
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
    return# resource

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
        return# resource
    
    content = private['scrapedData']['content']
    clean_content = extract_clean_content(content)
    if not clean_content:
        private['cleanContent'] = { "error" : "Could not clean content." }
        girder_db.item.update({'_id': item_id}, resource)
        return# resource
    private['cleanContent'] = { 'content' : clean_content }
    
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
    girder_db.item.update({'_id': item_id}, resource)
    return# resource
