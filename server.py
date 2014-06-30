import json
import pickle
import flask
from flask import render_template, request

import config

from celery import chain
import tasks

import bson
import pymongo
girder_db = pymongo.Connection(config.mongo_url)['girder']

import datetime
def my_serializer(obj):
    """
    Serializes dates, ObjectIds and potentially other useful things
    """
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, bson.ObjectId):
        return str(obj)
    else:
        raise TypeError(obj)

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
    
app = flask.Flask(__name__)

def get_values():
    """
    Return a dict with the request values, even if there is not mimetype.
    """
    if len(request.values) > 0:
        return request.values.to_dict()
    elif len(request.data) > 0:
        # data Contains the incoming request data as string if it came with a
        # mimetype Flask does not handle,
        # which happens when we get meteor posts from the diagnostic dashboard.
        return json.loads(request.data)
    return {}

@app.route('/test', methods = ['POST', 'GET'])
def test():
    return str(get_values())

@app.route('/diagnose', methods = ['POST', 'GET'])
def diagnosis():
    content = get_values().get('content')
    return json.dumps(my_diagnoser.diagnose(content), default=my_serializer)

@app.route('/beta/enqueue_girder_diagnosis/<item_id>', methods = ['POST', 'GET'])
def enqueue_diagnosis(item_id):
    item_id = bson.ObjectId(item_id)
    if girder_db.item.find_one(item_id):
        girder_db.item.update({'_id':item_id}, {
            '$set': {
                'meta.processing' : True,
                'meta.diagnosing' : True
            }
        })
        chain(
            tasks.process_girder_resource.s(item_id=item_id).set(queue='priority'),
            tasks.diagnose_girder_resource.s(item_id=item_id)
        )()
        return flask.jsonify(
             success=True
        )
    else:
        return flask.jsonify(
             success=False
        )

@app.route('/beta/counts', methods = ['POST', 'GET'])
def searchCounts():
    params = get_values()
    count_types = ["caseCount", "hospitalizationCount", "deathCount"]
    disease = params.get('disease', '')
    cursor = girder_db.item.find({
        '$and' : [{
                'meta.diagnosis.diseases.name': disease
            }] + [{
                'meta.diagnosis.features.type': {
                    '$in' : count_types
                }
            }] + [{
                'meta.diagnosis.features.type': 'datetime'
            }] + [{
                'meta.diagnosis.diagnoserVersion': '0.0.2'
            }]
    }, {'meta.diagnosis.features' : 1})
    result = []
    def offset_difference(a,b):
        if a['textOffsets'][0] > b['textOffsets'][0]:
            return offset_difference(b,a)
        return b['textOffsets'][0] - a['textOffsets'][1]
    
    for item in cursor:
        counts = []
        datetimes = []
        for feature in item['meta']['diagnosis']['features']:
            if feature['type'] in count_types:
                counts.append(feature)
            elif feature['type'] == 'datetime':
                datetimes.append(feature)
        
        # Annotate counts with datetimes based on proximity
        for count in counts:
            for dt in datetimes:
                if isinstance(dt['textOffsets'][0], list):
                    dt['textOffsets'] = dt['textOffsets'][0]
                if 'datetime' in count:
                    if offset_difference(count, dt) >= offset_difference(count['datetime'], dt):
                        continue
                if offset_difference(count, dt) < 300:
                    count['datetime'] = dt
    
        result.append({
            '_id' : item['_id'],
            'counts' : counts
        })
    
    
    return json.dumps(result, default=my_serializer)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-debug', action='store_true')
    args = parser.parse_args()
    app.run(host='0.0.0.0', debug=args.debug)
