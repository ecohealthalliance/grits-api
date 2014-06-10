import celery
import json
import pickle
import diagnosis
import pymongo
from celery import Celery
import datetime

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
    
@celery_tasks.task
def diagnose_girder_resource(prev, item_id=None):
    """
    Run the diagnostic classifiers/feature extractors
    on the girder item with the given id.
    """
    resource = girder_db.item.find_one(item_id)
    clean_english_content = resource.get('private', {}).get('clean_content_en')
    if clean_english_content:
        diagnosis = my_diagnoser.diagnose(clean_english_content)
    else:
        diagnosis = { 'error' : 'No content available to diagnose.' }
    diagnosis['apiVersion'] = '0.0.0'
    diagnosis['dateOfDiagnosis'] = datetime.datetime.now() 
    girder_db.item.update({'_id': item_id}, {
        '$set': {
            'meta.diagnosis' : diagnosis,
        },
        '$unset': {
            'meta.diagnosing' : '',
        }
    })
    return resource

from corpora_shared.process_resources import extract_clean_content, attach_translations
from corpora_shared import translation
from corpora_shared.scrape import scrape
@celery_tasks.task
def process_girder_resource(item_id=None):
    """
    Scrape the meta.link of the girder item with the given id.
    Update the entry with the results, then update it with cleaned and 
    translated versions of the scraped content.
    """
    resource = girder_db.item.find_one(item_id)
    scraped_data = scrape(resource['meta']['link'])
    if scraped_data.get('unscrapable'):
        girder_db.item.update({'_id': item_id}, {
            '$set': {
                'private.scraped_data': scraped_data,
            },
            '$unset': {
                'meta.processing' : '',
                'meta.diagnosing' : '',
            }
        })
        return
    content = scraped_data['content']
    clean_content = extract_clean_content(content)
    if not clean_content:
        girder_db.item.update({'_id': item_id}, {
            '$set': {
                'meta.error': "Could not clean content.",
            },
            '$unset': {
                'meta.processing' : '',
                'meta.diagnosing' : '',
            }
        })
        return
    clean_content_en = clean_content
    if not translation.is_english(clean_content):
        clean_content_en = translation.get_translation(str(item_id))
    girder_db.item.update({'_id': item_id}, {
        '$set': {
            'private.scraped_data': scraped_data,
            'private.clean_content': clean_content,
            'private.clean_content_en' : clean_content_en,
        },
        '$unset': {
            'meta.processing' : '',
        }
    })
