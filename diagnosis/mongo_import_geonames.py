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

def parse_number(num, default):
    try:
        return int(num)
    except ValueError:
        try:
            return float(num)
        except ValueError:
            return default
        
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
            names = [d['name']]
            if len(d['alternatenames']) > 0:
                names += d['alternatenames'].split(',')
            for name in set(names):
                yield dict(d, lemmatized_name=name.lower())

if __name__ == '__main__':
    print "This takes me about a half hour to run on my machine..."
    db = pymongo.Connection('localhost', port=27017)['geonames']
    collection = db['allCountries']
    collection.drop()
    for i, geoname in enumerate(read_geonames_csv('allCountries.txt')):
        total_row_estimate = 10000000
        if i % (total_row_estimate / 10) == 0:
            print i, '/', total_row_estimate, '+ geonames imported'
        collection.insert(geoname)
    db.allCountries.ensure_index('lemmatized_name')
    # Test that the collection contains some of the locations we would expect:
    test_names = ['yosemite', 'new york', 'africa', 'canada']
    query = db.allCountries.find({ 'lemmatized_name' : { '$in' : test_names } })
    found_names = set([geoname['lemmatized_name'] for geoname in query])
    assert set(test_names) - found_names == set()
