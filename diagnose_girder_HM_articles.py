"""
Check for undiagnosed articles in girder and diagnose them.
"""
import pymongo
import tasks_preprocess
import tasks_diagnose
import datetime
from celery import chain
from diagnosis.Diagnoser import Diagnoser

def update():
    print "Cleaning up old tasks..."
    girder_db = pymongo.Connection('localhost')['girder']
    # Cleans up completed task metadata older than a day.
    # Celery beat could do this, but we're not running it at the moment.
    # As an aside, the mongo tasks database will continue to have a large 
    # fileSize even after it is cleaned because it is preallocated.
    tasks_preprocess.celery_tasks.backend.cleanup()
    print "Queueing unprocessed and out-of-date HealthMap alerts for processing..."
    print "Current diagnoser version:", Diagnoser.__version__
    print "Current preprocessor version:", tasks_preprocess.processor_version
    resources_queued = 0
    while True:
        resources = girder_db.item.find({
            '$or' : [
                {
                    'meta.diagnosis' : { "$exists": False }
                }, {
                    'private.processorVersion' : {
                        '$ne' : tasks_preprocess.processor_version
                    }
                }, {
                    'meta.diagnosis.error' : { "$exists": False },
                    'meta.diagnosis.diagnoserVersion' : {
                        '$ne' : Diagnoser.__version__
                    }
                }
            ],
            # Only enqueue articles if they were not recently enqueued
            'meta.processingQueuedOn' : {
                '$not' : {
                    '$gt' : datetime.datetime.utcnow() - datetime.timedelta(1)
                }
            }
        }).limit(300)
        resources_in_cursor = 0
        for resource in resources:
            item_id = resource['_id']
            girder_db.item.update({'_id':item_id}, {
                '$set': {
                    'meta.processing' : True,
                    'meta.diagnosing' : True,
                    'meta.processingQueuedOn' : datetime.datetime.utcnow()
                }
            })
            chain(
                tasks_preprocess.process_girder_resource.s(
                    item_id=str(item_id)).set(queue='process'),
                tasks_diagnose.diagnose_girder_resource.s(
                    item_id=str(item_id)).set(queue='diagnose')
            )()
            resources_in_cursor += 1
        if resources_in_cursor == 0:
            break
        resources_queued += resources_in_cursor
        print "Resources queued for processing so far:", resources_queued

if __name__ == "__main__":
    update()
