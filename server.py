import json

import config

from celery import chain
import tasks

import bson
import pymongo
girder_db = pymongo.Connection(config.mongo_url)['girder']

import datetime

import tornado.ioloop
import tornado.web

class DiagnoseHandler(tornado.web.RequestHandler):
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
            task = chain(
                tasks.diagnose.s({
                    'cleanContent' : dict(content=content)
                }).set(queue='priority')
            )()
        elif url:
            task = chain(
                tasks.scrape.s(url).set(queue='priority'),
                tasks.process_text.s().set(queue='priority'),
                tasks.diagnose.s().set(queue='priority')
            )()
        else:
            self.write({
                'error' : "Please provide a url or content to diagnose."
            })
            self.set_header("Content-Type", "application/json")  
            self.finish()
            return
        
        def check_celery_task():
            if task.ready():
                self.write(task.get())
                self.set_header("Content-Type", "application/json")  
                self.finish()
            else:   
                tornado.ioloop.IOLoop.instance().add_timeout(datetime.timedelta(0,6), check_celery_task)

        check_celery_task()

    @tornado.web.asynchronous
    def post(self):
        return self.get()

class PublicDiagnoseHandler(DiagnoseHandler):
    @tornado.web.asynchronous
    def get(self):
        api_key = self.get_argument("api_key")
        if api_key == 'grits28754':
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
    #parser.add_argument('-debug', action='store_true')
    args = parser.parse_args()
    application.listen(5000)
    tornado.ioloop.IOLoop.instance().start()
