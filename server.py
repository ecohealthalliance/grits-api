import json
import pickle
import flask
from flask import render_template, request

from celery import chain
import tasks

import bson
import pymongo
girder_db = pymongo.Connection('localhost')['girder']

import datetime
def date_serializer(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    else:
        raise TypeError()

from diagnosis.Diagnoser import Diagnoser
with open('diagnoser.p', 'rb') as f:
    my_diagnoser = pickle.load(f)
    
app = flask.Flask(__name__)

@app.route('/diagnose', methods = ['POST', 'GET'])
def diagnosis():
    data = request.values
    content = data.get('content')
    return json.dumps(my_diagnoser.diagnose(content), default=date_serializer)
    
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
