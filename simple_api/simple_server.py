import json
import pickle

import tornado.ioloop
import tornado.web
import tornado.httpclient

import datetime
from SimpleDiagnoser import SimpleDiagnoser

with open('current_classifier/classifier.p') as f:
    my_classifier = pickle.load(f)
with open('current_classifier/dict_vectorizer.p') as f:
    my_dict_vectorizer = pickle.load(f)
with open('current_classifier/keyword_array.p') as f:
    keyword_array = pickle.load(f)

def make_json_compat(obj):
    """
    Coerce the types in an object to values that can be jsonified.
    """
    base_types = [str, unicode, basestring, bool, int, long, float, type(None)]
    if type(obj) in base_types:
        return obj
    elif isinstance(obj, list):
        return map(make_json_compat, obj)
    elif isinstance(obj, dict):
        return { k : make_json_compat(v) for k,v in obj.items() }
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, bson.ObjectId):
        return str(obj)
    else:
        raise TypeError(type(obj))

diagnoser = SimpleDiagnoser(
    my_classifier,
    my_dict_vectorizer,
    keyword_array=keyword_array,
    cutoff_ratio=.7
)

class ClassifyHandler(tornado.web.RequestHandler):
    def get(self):
        try:
            params = json.loads(self.request.body)
        except ValueError as e:
            params = {}

        content = self.get_argument('content', params.get('content'))
        if not content:
            print self.request.body
        self.write(make_json_compat(diagnoser.diagnose(content)))
        self.write("\n")
        self.set_header("Content-Type", "application/json")
        self.finish()
    def post(self):
        return self.get()

application = tornado.web.Application([
    (r"/classify", ClassifyHandler)
])

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    import logging
    logging.getLogger().setLevel(logging.INFO)
    application.listen(5000)
    tornado.ioloop.IOLoop.instance().start()
