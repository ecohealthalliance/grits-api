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

from annotator import prof

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
                tasks.diagnose.s({
                    'cleanContent' : dict(content=content)
                }).set(queue='priority')
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
                    return
                if not self.public and task.parent:
                    resp['scrapedData'] = task.parent.get()
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

class CprofileHandler(tornado.web.RequestHandler):
    public = True
    @tornado.web.asynchronous
    def get(self):
        api_key = self.get_argument('api_key')
        sort_by = self.get_argument('sort_by', 'cumulative_time')
        if api_key == config.api_key:
            self.write(prof.get_cprofile_table(sort_by=sort_by))
            self.finish()
        else:
            self.send_error(401)

class ProfileHandler(tornado.web.RequestHandler):
    public = True
    @tornado.web.asynchronous
    def get(self):
        api_key = self.get_argument('api_key')
        sort_by = self.get_argument('sort_by', 'cumulative_time')
        if api_key == config.api_key:
            self.write(prof.get_profile_table(sort_by=sort_by))
            self.finish()
        else:
            self.send_error(401)

application = tornado.web.Application([
    (r"/test", TestHandler),
    (r"/diagnose", DiagnoseHandler),
    (r"/public_diagnose", PublicDiagnoseHandler),
    (r"/cprofile", CprofileHandler),
    (r"/profile", ProfileHandler)
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
