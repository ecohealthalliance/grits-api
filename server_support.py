
import urlparse
import re

import celery
import tasks


def handleDiagnosis(content=None, url=None):
    """
    Framework agnostic handler for the diagnose endpoint.  Takes the
    `content` and `url` parameters provided to the endpoint and checks
    that they are valid.

    The method returns a function that can be called to get the status of
    task.  This function returns a dictionary:

    {
        'status': 'success' | 'pending' | 'failure'
        'message': string : providing detail of the status (i.e. failure message)
        'result': dict : On success gives the result of the diagnosis task
        'content': dict : The data scraped from the url (or given as content)
    }

    """

    response = {
        "status": "pending",
        "message": "",
        "result": None,
        "content": None
    }

    task = None
    results = []
    res_set = None

    # The method returned to get the status of the diagnosis
    def statusQuery():

        if response["status"] != "pending":
            # The task is running, but not finished
            return response
        try:
            resp = task.get()
        except Exception as e:
            # Some unknown failure, returns the exception
            response["status"] = "failure"
            response["message"] = unicode(e)
            return response

        if res_set.failed():
            # Task failure
            response["status"] = "failure"
            response["message"] = "One or more celery tasks failed"
            return response

        if res_set.ready():
            # Tasks complete, populate the response
            response["status"] = "success"
            response["result"] = resp
            if task.parent:
                response["content"] = task.parent.get()
            else:
                response["content"] = {}

        return response

    # Check the parameters and start the celery task
    if content:
        task = celery.chain(
            tasks.diagnose.s({
                'cleanContent': dict(content=content)
            }).set(queue='priority')
        )()
    elif url:
        hostname = ""
        try:
            hostname = urlparse.urlparse(url).hostname or ""
        except Exception:
            pass

        if not re.match(r".+\.\D+", hostname):
            response["status"] = "failure"
            response["message"] = "Invalid URL"
        else:
            task = celery.chain(
                tasks.scrape.s(url).set(queue='priority'),
                tasks.process_text.s().set(queue='priority'),
                tasks.diagnose.s().set(queue='priority')
            )()
    else:
        response["status"] = "failure"
        response["message"] = "Please provide a url or content to diagnose."

    if task is not None:
        r = task
        while r.parent:
            results.append(r.parent)
            r = r.parent
        res_set = celery.result.ResultSet(results)

    return statusQuery
