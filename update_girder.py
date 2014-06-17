"""
Check for undiagnosed articles in girder and diagnose them.
"""
import pymongo
import tasks
from celery import chain

if __name__ == "__main__":
    girder_db = pymongo.Connection('localhost')['girder']
    resources = girder_db.item.find({
        'meta.diagnosis' : {"$exists": False},
        'private.scrapedData.unscrapable' : { '$ne' : True }
    }).batch_size(100)
    print "Resources to process:", resources.count()
    for idx, resource in enumerate(resources):
        if idx % (resources.count() / 10) == 0:
            print "At resource", idx, "of", resources.count()
        item_id = resource['_id']
        girder_db.item.update({'_id':item_id}, {
            '$set': {
                'meta.processing' : True,
                'meta.diagnosing' : True
            }
        })
        chain(
            tasks.process_girder_resource.s(item_id=item_id),
            tasks.diagnose_girder_resource.s(item_id=item_id)
        )()
