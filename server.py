import json
import pickle
import flask
from flask import render_template, request, abort, jsonify, Response
import numpy

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
    if isinstance(obj, numpy.int64):
        return int(obj)
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

app = flask.Flask(__name__, static_url_path='')

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

@app.route('/public_diagnose', methods = ['POST', 'GET'])
def public_diagnosis():
    content = get_values().get('content')
    api_key = get_values().get('api_key')
    if api_key == 'grits28754':
        return Response(json.dumps(my_diagnoser.diagnose(content), default=my_serializer),
                        mimetype='application/json')
    else:
        abort(401)


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


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-debug', action='store_true')
    args = parser.parse_args()
    app.run(host='0.0.0.0', debug=args.debug)
