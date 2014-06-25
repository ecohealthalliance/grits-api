#!/usr/bin/env python

import sys
import os
import dateutil.parser
import datetime

import pymongo

import requests

import girder
from girder.utility import server, model_importer


def loadConfig():
    # return server config and healthmap authentication
    apikey = os.environ.get('HEALTHMAP_APIKEY')
    if apikey is None:
        raise Exception("HEALTHMAP_APIKEY is not set.")
    config = {
        'girderUsername': 'grits',
        'girderCollectionName': 'healthMap',
        'healthMapRoot': 'http://healthmap.org/HMapi.php',
        'healthMapDayFMT': '%Y-%m-%d',
        'allAlertsFolder': 'allAlerts',
    }
    config['healthMapApiKey'] = apikey
    return config


def loadHMap(config, day):
    # load healthMap alerts from the web api
    oneDay = datetime.timedelta(1)
    params = {
        'auth': config['healthMapApiKey'],
        'striphtml': '1',
        'sdate': day.strftime(config['healthMapDayFMT']),
        'edate': (day + oneDay).strftime(config['healthMapDayFMT'])
    }

    response = requests.get(config['healthMapRoot'], params=params)
    if not response.ok:
        raise Exception('Error requesting health map data.')

    # flatten the records
    records = response.json()
    allAlerts = []
    for record in records:
        n = 0
        alerts = record.pop('alerts')
        for alert in alerts:
            alert.update(record)
            id = '%s%04i' % (idFromURL(alert['link']), n)
            alert['id'] = id
            allAlerts.append(alert)
            n = n + 1
    return allAlerts


def idFromURL(url):
    # parse the healthmap id from the link url
    l = url.split('?')
    id = l[1].split('&')[0]
    return int(id)


def filterAlert(alert):
    # do any per alert data filtering here
    try:
        alert['rating'] = int(float(alert['rating']['rating']))
    except Exception:
        alert['rating'] = -1
    alert['date'] = dateutil.parser.parse(alert['formatted_date'])
    alert['updated'] = datetime.datetime.now()
    try:
        alert['lat'] = float(alert['lat'])
        alert['lng'] = float(alert['lng'])
    except ValueError:
        alert['lat'] = None
        alert['lng'] = None

    return alert


def girderSearch(m, query):
    return list(m.find(query))


def setupGirder():
    server.setup()
    model = model_importer.ModelImporter()
    models = {
        'collection': model.model('collection'),
        'folder': model.model('folder'),
        'item': model.model('item'),
        'user': model.model('user')
    }
    return models


def main(*args):

    # open config file
    config = loadConfig()

    # initialize girder models
    model = setupGirder()

    # get user id
    response = girderSearch(model['user'], {'login': config['girderUsername']})
    if len(response) == 0:
        raise Exception("User '%s' does not exist" % config['girderUsername'])
    user = response[0]

    # get collection ID
    response = girderSearch(
        model['collection'],
        {'name': config['girderCollectionName']}
    )
    if len(response) > 0:
        collection = response[0]
    else:
        raise Exception("Could not find healthmap collection.")

    # get the folder containing all of the alerts
    response = girderSearch(model['folder'], {'name': config['allAlertsFolder'],
                                              'parentCollection': 'collection',
                                              'parentId': collection['_id']})
    if len(response) > 0:
        folder = response[0]
    else:
        raise Exception("Could not find healthmap folder.")

    # get the date range to download, defaults to the last 1 day
    if len(args) >= 1:
        # arg 1 start day
        start = dateutil.parser.parse(args[0])
    else:
        start = datetime.datetime.now() - datetime.timedelta(1)
    if len(args) >= 2:
        end = dateutil.parser.parse(args[1])
    else:
        end = start + datetime.timedelta(1)

    nAdded = 0
    nUpdated = 0

    # loop through all days in the range
    while start < end:
        print 'Downloading data from %s...' % start.strftime('%Y-%m-%d')
        alerts = loadHMap(config, start)
        print 'Received %i alerts, adding to girder...' % len(alerts)

        # loop through all alerts in the response
        for alert in alerts:

            # process the data
            alert = filterAlert(alert)
            meta = {
                'latitude': alert.get('lat'),
                'longitude': alert.get('lng'),
                'date': alert.get('date'),
                'feed': alert.get('feed'),
                'link': alert.get('original_url', alert.get('link')),
                'country': alert.get('country'),
                'disease': alert.get('disease'),
                'rating': alert.get('rating'),
                'species': alert.get('species_name'),
                'description': alert.get('descr', '')
            }
            desc = alert.get('summary', alert.get('summary_en', ''))

            # check if the item already exists
            items = girderSearch(model['item'], {
                'name': str(alert['id']),
                'folderId': folder['_id']
            })

            if len(items) > 1:
                print >> sys.stderr, \
                    'WARNING: multiple items with the same name exist'

                # delete the items with this name, which should be unique
                for item in items[1:]:
                    model['item'].remove(item)

            if len(items) > 0:
                # update item
                item = items[0]
                item['description'] = desc
                nUpdated += 1

            else:
                # create the item
                item = model['item'].createItem(
                    str(alert['id']),
                    user,
                    folder,
                    description=desc
                )
                nAdded += 1

            # add/update metadata
            item['meta'] = meta
            model['item'].save(item, validate=False)

        start = start + datetime.timedelta(1)
    print 'Added %i new items' % nAdded
    print 'Updated %i old items' % nUpdated

if __name__ == '__main__':
    import sys
    now = datetime.datetime.now()
    fmt = '%Y-%m-%d'
    if len(sys.argv) < 2 or sys.argv[1] == '--day':
        yesterday = now - datetime.timedelta(1)
        args = [yesterday, now]
        args = [a.strftime(fmt) for a in args]
    elif sys.argv[1] == '--twoday':
        yesterday = now - datetime.timedelta(2)
        args = [yesterday, now]
        args = [a.strftime(fmt) for a in args]
    elif sys.argv[1] == '--full':
        start = datetime.datetime(now.year - 2, now.month, now.day)
        args = [start, now]
        args = [a.strftime(fmt) for a in args]
    elif sys.argv[1] == '--month':
        start = now - datetime.timedelta(days=31)
        args = [start, now]
        args = [a.strftime(fmt) for a in args]
    else:
        args = sys.argv[1:]
    main(*args)
