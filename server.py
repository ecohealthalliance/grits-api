import json
import pickle
import flask
from flask import render_template, request

import tasks

import bson
import pymongo
db = pymongo.Connection('localhost', port=27017)['girder']

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

@app.route('/enqueue_diagnosis', methods = ['POST', 'GET'])
def enqueue_diagnosis():
    data = request.values.to_dict()
    item_id = str(bson.ObjectId())
    if 'link' in data:
        for item in db.item.find({'meta.link': data['link']}):
            return flask.jsonify(item)
        db.item.insert({
            '_id': item_id,
            'diagnosing' : True,
            'meta' : { 'link' : data['link'] }
        })
        return flask.jsonify(
            _id=item_id,
            task_id=tasks.scrape_and_diagnose.delay(data, item_id=item_id).id
        )
    else:
        db.item.insert({'_id': item_id, 'diagnosing' : True})
        return flask.jsonify(
            _id=item_id,
            task_id=tasks.diagnose.delay(data, item_id=item_id).id
        )

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
