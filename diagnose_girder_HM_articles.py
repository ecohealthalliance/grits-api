"""
Check for undiagnosed articles in girder and diagnose them.
"""
import pymongo
import tasks
from celery import chain
import datetime

def update():
    girder_db = pymongo.Connection('localhost')['girder']
    while True:
        resources = girder_db.item.find({
            'meta.diagnosis.diagnoserVersion' : { '$ne' : '0.0.3' },
            # select only items that are not being diagnosed, 
            # or where the diagnosis has taken more than a day.
            '$or' : [{'meta.processingQueuedOn' : None}, {
                'meta.processingQueuedOn' : {
                    '$lt' : datetime.datetime.utcnow() - datetime.timedelta(1)
                }
            }, {
                'meta.processing' : { '$ne' : True },
                'meta.diagnosing' : { '$ne' : True },
            }],
            'private.scrapedData.unscrapable' : { '$ne' : True }
        }).limit(200)
        remaining_resources = resources.count()
        if remaining_resources == 0:
            break
        print "Remaining resources to process:", remaining_resources
        for resource in resources:
            item_id = resource['_id']
            girder_db.item.update({'_id':item_id}, {
                '$set': {
                    'meta.processingQueuedOn' : datetime.datetime.utcnow(),
                    'meta.processing' : True,
                    'meta.diagnosing' : True
                }
            })
            chain(
                tasks.process_girder_resource.s(item_id=str(item_id)).set(queue='process'),
                tasks.diagnose_girder_resource.s(item_id=str(item_id)).set(queue='diagnose')
            )()

if __name__ == "__main__":
    update()
