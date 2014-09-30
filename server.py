import json

import config

import celery
import tasks

import bson
import pymongo
girder_db = pymongo.Connection(config.mongo_url)['girder']

import datetime

import tornado.ioloop
import tornado.web

import urlparse
import re

from server_support import handleDiagnosis

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

        statusCallback = handleDiagnosis(content=content, url=url)

        def checkStatus():
            statusObj = statusCallback()

            if statusObj["status"] == "failure":
                self.write({
                    "error": statusObj["message"]
                })
                self.set_header("Content-Type", "application/json")
                self.finish()
            elif statusObj["status"] == "success":
                response = statusObj["result"]

                if not self.public:
                    response["scrapedData"] = statusObj["content"]

                self.write(response)
                self.set_header("Content-Type", "application/json")
                self.finish()
            else:
                tornado.ioloop.IOLoop.instance().add_timeout(
                    datetime.timedelta(0, 1), checkStatus
                )

        checkStatus()

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

application = tornado.web.Application([
    (r"/test", TestHandler),
    (r"/diagnose", DiagnoseHandler),
    (r"/public_diagnose", PublicDiagnoseHandler)
])

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-debug', action='store_true')
    args = parser.parse_args()
    if args.debug:
        # Run tasks in the current process so we don't have to run a worker
        # when debugging.
        tasks.celery_tasks.conf.update(
            CELERY_ALWAYS_EAGER = True,
        )
    application.listen(5000)
    tornado.ioloop.IOLoop.instance().start()
