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

@app.route('/diagnose', methods = ['POST', 'GET'])
def diagnosis():
    data = request.values
    content = data.get('content')
    return json.dumps(my_diagnoser.diagnose(content), default=my_serializer)
    
@app.route('/enqueue_girder_diagnosis/<item_id>', methods = ['POST', 'GET'])
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
            tasks.process_girder_resource.s(item_id=item_id),
            tasks.diagnose_girder_resource.s(item_id=item_id)
        )()
        return flask.jsonify(
             success=True
        )
    else:
        return flask.jsonify(
             success=False
        )

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
