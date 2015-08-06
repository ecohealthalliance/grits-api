import json

import config

import celery
import tasks_diagnose
import tasks_preprocess

import bson
import pymongo
girder_db = pymongo.Connection(config.mongo_url)['girder']

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

class DiagnoseHandler(tornado.web.RequestHandler):
    public = False
    @tornado.web.asynchronous
    def get(self):
        # Try to parse the json bodies submitted by the diagnostic dash:
        try:
            params = json.loads(self.request.body)
        except ValueError as e:
            params = {}

        content = self.get_argument('content', params.get('content'))
        url = self.get_argument('url', params.get('url'))
        if content:
            task = celery.chain(
                tasks_preprocess.process_text.s({
                    'content' : content
                }).set(queue='priority'),
                tasks_diagnose.diagnose.s().set(queue='priority')
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
                tasks_diagnose.diagnose.s().set(queue='priority')
            )()
        else:
            self.write({
                'error' : "Please provide a url or content to diagnose."
            })
            self.set_header("Content-Type", "application/json")
            self.finish()
            return

        # Create a result set so we can check all the tasks in the chain for
        # failure status.
        r = task
        results = [r]
        while r.parent:
            results.append(r.parent)
            r = r.parent
        res_set = celery.result.ResultSet(results)

        def check_celery_task():
            if res_set.ready() or res_set.failed():
                try:
                    resp = task.get()
                except Exception as e:
                    self.write({
                        'error' : unicode(e)
                    })
                    self.set_header("Content-Type", "application/json")
                    self.finish()
                    if 'args' in globals() and args.debug:
                        raise e
                    return
                if self.get_argument('returnSourceContent',
                    params.get('returnSourceContent', False)):
                    resp['source'] = task.parent.get()
                self.write(resp)
                self.set_header("Content-Type", "application/json")
                self.finish()
            else:
                tornado.ioloop.IOLoop.instance().add_timeout(
                    datetime.timedelta(0,1), check_celery_task
                )

        check_celery_task()

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
    @tornado.web.asynchronous
    def post(self):
        endpoint = "http://search.bsvecosystem.net"
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
        def make_search_result_cb(request_id):
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
                            endpoint + "/api/search/v1/result?requestId=%s" % request_id,
                            headers={
                                "harbinger-authentication": auth_header
                            },
                            method="GET"), search_result_cb))
                elif parsed_resp['status'] == -1:
                    self.set_status(500)
                    self.write('Result Error:\n' + resp.body)
                    self.finish()
                else:
                    self.write(resp.body)
                    self.set_header("Content-Type", "application/json")
                    self.finish()
            return search_result_cb
        def search_request_cb(resp):
            if resp.error:
                self.set_status(500)
                self.write('Request Error:\n' + str(resp.error))
                self.finish()
            else:
                client.fetch(tornado.httpclient.HTTPRequest(
                    endpoint + "/api/search/v1/result?requestId=%s" % resp.body,
                    headers={
                        "harbinger-authentication": auth_header
                    },
                    method="GET"), make_search_result_cb(resp.body))
        bsve_path = self.request.path.split('/bsve')[1]
        if bsve_path == "/search":
            client.fetch(tornado.httpclient.HTTPRequest(
                endpoint + "/api/search/v1/request",
                headers={
                    "harbinger-authentication": auth_header,
                    "Content-Type": "application/json; charset=utf8"
                },
                method="POST",
                body=self.request.body), search_request_cb)
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
