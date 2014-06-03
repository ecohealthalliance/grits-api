import celery
import json
import pickle
import diagnosis
import pymongo
from celery import Celery

BROKER_URL = 'mongodb://localhost:27017/tasks'
celery_tasks = Celery('tasks', broker=BROKER_URL)
db = pymongo.Connection('localhost')['girder']

import datetime
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
def diagnose(data, item_id=None):
    content = data['content']
    diagnosis = my_diagnoser.diagnose(content)
    db.item.update({'_id': item_id}, {
        '$set': {
            'private': {
                'full_text': content
            },
            'diagnosis': serialize_dates(diagnosis),
            'diagnosing' : False
        }
    })

from corpora.process_resources import process_resource
from corpora.scrape import scrape
@celery_tasks.task
def scrape_and_diagnose(data, item_id=None):
    data.update(scrape(data['link']))
    # TODO: process_resource should not require the sourceMeta property.
    data['sourceMeta'] = data.get('sourceMeta', {})
    process_resource(data)
    return diagnose.delay(data, item_id=item_id)
