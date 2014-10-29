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
    # Reset the processing/diagnosing properties.
    # I think these should be phased out and replaced with processingQueuedOn
    girder_db.item.update(
        {}, {
            '$unset' : {
                'meta.processing':'',
                'meta.diagnosing':''
            }
        }, multi=True
    )
    print "Enqueuing diagnosis out of date articles..."
    print "Current diagnoser version:", Diagnoser.__version__
    print "Current preprocessor version:", tasks.processor_version
    while True:
        resources = girder_db.item.find({
            '$or' : [
                {
                    'meta.diagnosis' : { "$exists": False }
                }, {
                    'private.processorVersion' : { '$ne' : tasks.processor_version }
                }, {
                    'meta.diagnosis.error' : { "$exists": False },
                    'meta.diagnosis.diagnoserVersion' : { '$ne' : Diagnoser.__version__ }
                }
            ],
            # Only enqueue articles if they were not recently enqueued
            'meta.processingQueuedOn' : {
                '$not' : {
                    '$gt' : datetime.datetime.utcnow() - datetime.timedelta(1)
                }
            }
        }).limit(200)
        remaining_resources = resources.count()
        if remaining_resources == 0:
            print "No remaining resources to enqueue."
            break
        print "Remaining resources to enqueue:", remaining_resources
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
                tasks.process_girder_resource.s(item_id=str(item_id)).set(queue='process'),
                tasks.diagnose_girder_resource.s(item_id=str(item_id)).set(queue='diagnose')
            )()

if __name__ == "__main__":
    update()
