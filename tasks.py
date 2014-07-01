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

celery_tasks = Celery('tasks', broker=config.BROKER_URL)
celery_tasks.conf.update(
    CELERY_TASK_SERIALIZER='json',
    CELERY_ACCEPT_CONTENT=['json'],  # Ignore other content
    CELERY_RESULT_SERIALIZER='json'
)

db_handle = pymongo.Connection(config.mongo_url)
girder_db = db_handle['girder']
meteor_dash_db = db_handle['diagnosis']

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
def insert_case_counts(item_id, diagnosis):
    """
    Inserts the case counts into a collection in the meteor database.
    This is an experimental approach to doing this. One alternative is to use
    the flask API endpoint.
    
    A downside to this appraoch is that it will require lots of duplicate
    data to support all the ways we could filter diagnoses.
    Another issue is that updates to this code requires regenerating the collection.
    
    The advantage is that this code is coupled with the diagnoser
    we don't have to worry about checking diagnoser version.
    """
    # Remove old case counts for article
    meteor_dash_db['caseCounts'].remove({'itemId' : item_id})
    
    def offset_difference(a,b):
        if a['textOffsets'][0][0] > b['textOffsets'][0][0]:
            return offset_difference(b,a)
        return b['textOffsets'][0][0] - a['textOffsets'][0][1]
        
    count_types = ["caseCount", "hospitalizationCount", "deathCount"]
    
    result = []
    counts = []
    datetimes = []
    for feature in diagnosis.get('features', []):
        if feature['type'] in count_types:
            counts.append(feature)
        elif feature['type'] == 'datetime':
            datetimes.append(feature)
    
    # Annotate counts with datetimes based on proximity
    for count in counts:
        for dt in datetimes:
            if 'datetime' in count:
                if offset_difference(count, dt) >= offset_difference(count['datetime'], dt):
                    continue
            if offset_difference(count, dt) < 300:
                count['datetime'] = dt
        
        count.update({
            'itemId' : item_id,
            # Add locations?
            'diseases' : [d['name'] for d in diagnosis['diseases']]
        })
        result.append(count)
        
    if len(result) > 0:
        meteor_dash_db['caseCounts'].insert(result)

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
        return
    translation = resource['private'].get('translation')
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
    
    insert_case_counts(item_id, meta['diagnosis'])
    return

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
    item_id = bson.ObjectId(item_id)
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
        girder_db.item.update({'_id': item_id}, resource)
        return
    
    content = private['scrapedData']['content']
    clean_content = extract_clean_content(content)
    if not clean_content:
        private['cleanContent'] = { "error" : "Could not clean content." }
        girder_db.item.update({'_id': item_id}, resource)
        return
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
    return
