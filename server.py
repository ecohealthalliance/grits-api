import json
import flask
from flask import render_template, request
from diagnose import diagnose

app = flask.Flask(__name__)


@app.route('/diagnose', methods = ['POST', 'GET'])
def diagnosis():
    data = json.loads(request.data)
    content = data.get('content')
    diagnosis = diagnose(content)
    diseases = diagnosis['diseases']
    features = diagnosis['features'].keys()
    result = []
    for index, disease in enumerate(diseases):
        result.append({'name': disease, 'rank': index + 1, 'features': features})
    return json.dumps(result)

if __name__ == '__main__':
    app.run(host='localhost', debug=True)
