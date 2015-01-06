"""
Check for undiagnosed articles in girder and diagnose them.
"""
import pymongo
import tasks
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
    tasks.celery_tasks.backend.cleanup()
    print "Queueing unprocessed and out-of-date HealthMap alerts for processing..."
    print "Current diagnoser version:", Diagnoser.__version__
    print "Current preprocessor version:", tasks.processor_version
    resources_queued = 0
    while True:
        resources = girder_db.item.find({
            '$or' : [
                {
                    'meta.diagnosis' : { "$exists": False }
                }, {
                    'private.processorVersion' : {
                        '$ne' : tasks.processor_version
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
                tasks.process_girder_resource.s(
                    item_id=str(item_id)).set(queue='process'),
                tasks.diagnose_girder_resource.s(
                    item_id=str(item_id)).set(queue='diagnose')
            )()
            resources_queued += 1
        print "Resources queued for processing so far:", resources_queued

if __name__ == "__main__":
    update()
