import json
import pickle
import flask
from flask import render_template, request

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
    data = json.loads(request.data)
    content = data.get('content')
    return json.dumps(my_diagnoser.diagnose(content), default=date_serializer)

if __name__ == '__main__':
    app.run(host='localhost', debug=True)
