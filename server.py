import json
import flask
from flask import render_template, request
from diagnose import diagnose

app = flask.Flask(__name__)


@app.route('/diagnose', methods = ['POST'])
def diagnosis():
    data = json.loads(request.data)
    content = data.get('content')
    return json.dumps(diagnose(content))


if __name__ == '__main__':
    app.run(host='localhost', debug=True)
