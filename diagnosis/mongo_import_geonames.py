"""
Imports all the geonames in the CSV at file_path into the given Mongo collection.
I'm using Mongo to import geonames because it is too big to fit in memory
(even on a machine with over 4GB of available ram),
and the $in operator provides a fast way to search for all the ngrams in a document.

Geonames data is available here:
http://download.geonames.org/export/dump/
"""
import sys, csv
import unicodecsv
import pymongo
import config
import time

def parse_number(num, default):
    try:
        return int(num)
    except ValueError:
        try:
            return float(num)
        except ValueError:
            return default

def get_country_code_map():
    db = pymongo.Connection(config.mongo_url)['geonames']
    collection = db['countryInfo']

    country_code_map = {}

    for result in collection.find():
        country_code_map[result['ISO']] = result['Country']

    return country_code_map

def read_geonames_csv(file_path):
    geonames_fields=[
        'geonameid',
        'name',
        'asciiname',
        'alternatenames',
        'latitude',
        'longitude',
        'feature class',
        'feature code',
        'country code',
        'cc2',
        'admin1 code',
        'admin2 code',
        'admin3 code',
        'admin4 code',
        'population',
        'elevation',
        'dem',
        'timezone',
        'modification date',
    ]

    country_code_map = get_country_code_map()

    #Loading geonames data may cause errors without this line:
    csv.field_size_limit(2**32)
    with open(file_path, 'rb') as f:
        reader = unicodecsv.DictReader(f,
            fieldnames=geonames_fields,
            encoding='utf-8',
            delimiter='\t',
            quoting=csv.QUOTE_NONE)
        for d in reader:
            d['population'] = parse_number(d['population'], 0)
            d['latitude'] = parse_number(d['latitude'], 0)
            d['longitude'] = parse_number(d['longitude'], 0)
            d['elevation'] = parse_number(d['elevation'], 0)
            if len(d['alternatenames']) > 0:
                d['alternatenames'] = d['alternatenames'].split(',')
            else:
                d['alternatenames'] = []
            d['country'] = country_code_map[d['country code']]
            yield d

if __name__ == '__main__':
    print "This takes me about a half hour to run on my machine..."
    db = pymongo.Connection(config.mongo_url)['geonames']
    collection = db['allCountries']
    collection.drop()
    for i, geoname in enumerate(read_geonames_csv('allCountries.txt')):
        total_row_estimate = 10000000
        if i % (total_row_estimate / 10) == 0:
            print i, '/', total_row_estimate, '+ geonames imported'
        collection.insert(geoname)
    db.allCountries.ensure_index('name')
    db.allCountries.ensure_index('alternatenames')
    # Test that the collection contains some of the locations we would expect,
    # and that it completes in a reasonable amount of time.
    # TODO: Run the geoname extractor here.
    start_time = time.time()
    test_names = ['Riu Valira del Nord', 'Bosque de Soldeu', 'New York', 'Africa', 'Canada', 'Kirkland']
    query = db.allCountries.find({
        '$or' : [
            {
                'name' : { '$in' : test_names }
            },
            {
                'alternatenames' : { '$in' : test_names }
            }
        ]
    })
    found_names = set()
    for geoname in query:
        found_names.add(geoname['name'])
        for alt in geoname['alternatenames']:
            found_names.add(alt)
    difference = set(test_names) - found_names
    if difference != set():
        print "Test failed!"
        print "Missing names:", difference
    if time.time() - start_time > 15:
        print "Warning: query took over 15 seconds."
