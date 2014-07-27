"""
Check for undiagnosed articles in girder and diagnose them.
"""
import pymongo
import tasks
from celery import chain
from diagnosis.Diagnoser import Diagnoser

def update():
    print "Current diagnoser version:", Diagnoser.__version__
    print "Current preprocessor version:", tasks.processor_version
    girder_db = pymongo.Connection('localhost')['girder']
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
            'meta.processing' : { '$ne' : True },
            'meta.diagnosing' : { '$ne' : True }
        }).limit(200)
        remaining_resources = resources.count()
        if remaining_resources == 0:
            print "No remaining resources to process."
            break
        print "Remaining resources to process:", remaining_resources
        for resource in resources:
            item_id = resource['_id']
            girder_db.item.update({'_id':item_id}, {
                '$set': {
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
