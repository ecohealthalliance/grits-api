import json

import config

import celery
import tasks_diagnose
import tasks_preprocess

import bson
from pymongo import MongoClient
print "Connecting to mongoDB at", config.mongo_url
client = MongoClient(config.mongo_url)
girder_db = client.girder

import datetime

import tornado.ioloop
import tornado.web
import tornado.httpclient

import urlparse
import re

import hmac
import hashlib
import time
import random
import json
import dateutil.parser

def on_task_complete(task, callback):
    # if the task is a celery group with subtasks add them to the result set
    if hasattr(task, 'subtasks'):
        res_set = celery.result.ResultSet(task.subtasks)
    else:
        res_set = celery.result.ResultSet([task])
        # If the task is a chain, the parent tasks need to be added to the result set
        # to catch failures in them.
        task_ptr = task
        while task_ptr.parent:
            task_ptr = task_ptr.parent
            res_set.add(task_ptr)

    def check_celery_task():
        if res_set.ready() or res_set.failed():
            try:
                resp = task.get()
            except Exception as e:
                # When the debug parameter is passed in raise exceptions
                # instead of returning the error message.
                if 'args' in globals() and args.debug:
                    raise e
                # There is a bug in celery where exceptions are not properly marshaled
                # so the message is always "exceptions must be old-style classes or derived from BaseException, not dict"
                return callback(e, None)
            return callback(None, resp)
        else:
            tornado.ioloop.IOLoop.instance().add_timeout(
                datetime.timedelta(0,1), check_celery_task
            )
    check_celery_task()

class DiagnoseHandler(tornado.web.RequestHandler):
    public = False
    @tornado.web.asynchronous
    def get(self):
        print "Diagnose request received"
        # Try to parse the json bodies submitted by the diagnostic dash:
        try:
            params = json.loads(self.request.body)
        except ValueError as e:
            params = {}
        def get_bool_arg(key):
            val = self.get_argument(key, params.get(key, False))
            if isinstance(val, basestring):
                if val.lower() == "true":
                    return True
                elif val.lower() == "false":
                    return False
                else:
                    raise ValueError("Could not parse ", val)
            else:
                return val
        content = self.get_argument('content', params.get('content'))
        url = self.get_argument('url', params.get('url'))
        extra_args = {}
        content_date = self.get_argument('content_date', params.get('content_date'))
        if content_date:
            try:
                extra_args['content_date'] = dateutil.parser.parse(content_date)
            except ValueError:
                self.write({
                    'error' : "Could not parse content date"
                })
                self.set_header("Content-Type", "application/json")
                self.finish()
                return
        if content:
            task = celery.chain(
                tasks_preprocess.process_text.s({
                    'content' : content
                }).set(queue='priority'),
                tasks_diagnose.diagnose.s(extra_args).set(queue='priority')
            )()
        elif url:
            hostname = ""
            try:
                hostname = urlparse.urlparse(url).hostname or ""
            except:
                pass
            # Only allow hostnames that end with .word
            # This is to avoid the security vulnerability Russ pointed out where
            # we could end up scrapping localhost or IP addresses that should
            # not be publicly accessible.
            if not re.match(r".+\.\D+", hostname):
                self.write({
                    'error' : "Invalid URL"
                })
                self.set_header("Content-Type", "application/json")
                self.finish()
                return

            task = celery.chain(
                tasks_preprocess.scrape.s(url).set(queue='priority'),
                tasks_preprocess.process_text.s().set(queue='priority'),
                tasks_diagnose.diagnose.s(extra_args).set(queue='priority')
            )()
        else:
            self.write({
                'error' : "Please provide a url or content to diagnose."
            })
            self.set_header("Content-Type", "application/json")
            self.finish()
            return

        def callback(err, resp):
            if err:
                resp = {
                    'error': repr(err)
                }
            else:
                if get_bool_arg('returnSourceContent'):
                    # The parent task returns the processed text.
                    resp['source'] = task.parent.get()
            self.set_header("Content-Type", "application/json")
            self.write(resp)
            self.finish()
        on_task_complete(task, callback)


    @tornado.web.asynchronous
    def post(self):
        return self.get()

class PublicDiagnoseHandler(DiagnoseHandler):
    public = True
    @tornado.web.asynchronous
    def get(self):
        api_key = self.get_argument("api_key")
        if api_key == config.api_key:
            return super(PublicDiagnoseHandler, self).get()
        else:
            self.send_error(401)
    @tornado.web.asynchronous
    def post(self):
        return self.get()

class TestHandler(tornado.web.RequestHandler):
    def get(self):
        self.write(self.get_argument("url"))
        self.finish()
    def post(self):
        return self.get()

class BSVEHandler(tornado.web.RequestHandler):
    def get(self):
        return self.post()
    @tornado.web.asynchronous
    def post(self):
        if self.request.headers.get('Origin', "").endswith(".bsvecosystem.net"):
            self.set_header("Access-Control-Allow-Origin", "*")
        else:
            self.set_header("Access-Control-Allow-Origin", "https://bsvecosystem.net")
        timestamp = str(int(time.time() * 1e3))
        nonce = random.randint(0,100)
        hmac_key = "%s:%s" % (config.bsve_api_key, config.bsve_secret_key)
        hmac_message = "%s%s%s%s" % (config.bsve_api_key, timestamp, nonce, config.bsve_user_name)
        auth_header = "apikey=%s;timestamp=%s;nonce=%s;signature=%s" % (
            config.bsve_api_key,
            timestamp,
            nonce,
            hmac.new(hmac_key, msg=hmac_message, digestmod=hashlib.sha1).hexdigest())
        client = tornado.httpclient.AsyncHTTPClient()
        def bsve_search(callback):
            state = {'request_id' : None}
            def search_result_cb(resp):
                if resp.error:
                    self.set_status(500)
                    self.write('Result Error:\n' + str(resp.error))
                    self.finish()
                    return
                parsed_resp = json.loads(resp.body)
                if parsed_resp['status'] == 0:
                    tornado.ioloop.IOLoop.instance().add_timeout(
                        datetime.timedelta(0,1),
                        lambda: client.fetch(tornado.httpclient.HTTPRequest(
                            config.bsve_endpoint + "/api/search/v1/result?requestId=%s" % state['request_id'],
                            headers={
                                "harbinger-authentication": auth_header
                            },
                            method="GET"), search_result_cb))
                else:
                    callback(parsed_resp)
            def search_request_cb(resp):
                if resp.error:
                    self.set_status(500)
                    self.write('Request Error:\n' + str(resp.error))
                    self.finish()
                else:
                    state['request_id'] = resp.body
                    client.fetch(tornado.httpclient.HTTPRequest(
                        config.bsve_endpoint + "/api/search/v1/result?requestId=%s" % resp.body,
                        headers={
                            "harbinger-authentication": auth_header
                        },
                        method="GET"), search_result_cb)
            client.fetch(tornado.httpclient.HTTPRequest(
                config.bsve_endpoint + "/api/search/v1/request",
                headers={
                    "harbinger-authentication": auth_header,
                    "Content-Type": "application/json; charset=utf8"
                },
                method="POST",
                body=self.request.body), search_request_cb)
        bsve_path = self.request.path.split('/bsve')[1]
        if bsve_path == "/search":
            def search_finished(resp):
                self.write(resp)
                self.set_header("Content-Type", "application/json")
                self.finish()
            bsve_search(search_finished)
        elif bsve_path == "/search_and_diagnose":
            # The number of diagnoses are limited to prevent these requests
            # from taking too long.
            MAX_DIAGNOSES = 200
            def search_finished(search_resp):
                def task_finished(err, diagnoses):
                    self.set_header("Content-Type", "application/json")
                    if err:
                        print "ERROR:", err
                        self.write({
                            'error': repr(err)
                        })
                        self.finish()
                    else:
                        # Attach a diagnosis to each of the search results
                        # that one was computed for.
                        for result, diagnosis in zip(search_resp['results'], diagnoses):
                            result['diagnosis'] = diagnosis
                        self.write(search_resp)
                        self.finish()
                # Run a task chain that processes then diagnoses a search result
                # for each result in parallel.
                task = celery.group(celery.chain(
                    tasks_preprocess.process_text.s({
                        # The article title and content are classified.
                        # Unfortunately, the content returned in most search results in truncated
                        # to only a few sentences long. Links are included as well,
                        # however scraping the original sources would take several minutes.
                        'content': item['data']['Title'] + '\n' + item['data']['Content']
                    }).set(queue='priority'),
                    tasks_diagnose.diagnose.s(
                        # The diseases_only flag tells the diagnoser to only do classification
                        # (skipping location/date/case-count feature extraction) for speed.
                        # Classifications only take a fraction of a second.
                        dict(diseases_only=True)
                    ).set(queue='priority')
                ) for item in search_resp['results'][0:MAX_DIAGNOSES])()
                on_task_complete(task, task_finished)
            bsve_search(search_finished)
        elif bsve_path == "/feeds":
            def feeds_cb(resp):
                if resp.error:
                    self.set_status(500)
                    self.write('Feeds Error:\n' + str(resp.error))
                    self.finish()
                    return
                else:
                    self.write(resp.body)
                    self.set_header("Content-Type", "application/json")
                    self.finish()
            client.fetch(tornado.httpclient.HTTPRequest(
                config.bsve_endpoint + "/api/data/list/rss/feeds",
                headers={
                    "harbinger-authentication": auth_header,
                    "Content-Type": "application/json; charset=utf8"
                },
                method="GET"), feeds_cb)
        else:
            self.set_status(500)
            self.write('Error:\nBad Path')
            self.finish()

application = tornado.web.Application([
    (r"/test", TestHandler),
    (r"/diagnose", DiagnoseHandler),
    (r"/public_diagnose", PublicDiagnoseHandler),
    (r"/bsve/.*", BSVEHandler)
])

if __name__ == "__main__":
    print "Starting grits-api server..."
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-debug', action='store_true')
    args = parser.parse_args()
    if args.debug:
        # Run tasks in the current process so we don't have to run a worker
        # when debugging.
        tasks_diagnose.celery_tasks.conf.update(
            CELERY_ALWAYS_EAGER = True,
        )
    application.listen(5000)
    tornado.ioloop.IOLoop.instance().start()
