"""
Loading mongo with autocomplete data for the keywords and locations.
"""
import sys, csv
import re
import pickle
import config
import pymongo


def load_keyword_sets(file_path):
    with open(file_path) as f:
        keyword_sets = pickle.load(f)
    return keyword_sets

def insert_set(names_set, collection):
    """Insert a list of names into a collection"""

    for name in names_set:
        collection.insert({'_id': name})


if __name__ == '__main__':

    db = pymongo.Connection(config.mongo_url)['annotation']
    geonames_db = pymongo.Connection(config.mongo_url)['geonames']


    # We don't drop any collections, in case there are other sources for some
    # autocomplete data that have already run. But you should drop the
    # collection yourself before running this script if it has previously been
    # run. Otherwise, you'll notice duplicate key errors.

    ### Keywords ###

    keyword_sets = load_keyword_sets('keyword_sets.p')

    category_labels = [
        ('diseases', ['doid/diseases', 'pm/disease']),
        ('symptoms', ['biocaster/symptoms', 'doid/has_symptom', 'pm/symptom', 'symp/symptoms']),
        ('hosts', ['doid/transmitted_by', 'wordnet/hosts']),
        ('pathogens', ['wordnet/pathogens', 'biocaster/pathogens']),
        ('modes', ['pm/mode of transmission'])
    ]

    for category, labels in category_labels:
        collection = db[category]

        names_set = set()
        for label in labels:
            names_set = names_set.union(keyword_sets[label])

        insert_set(names_set, collection)

    ### Locations ###

    res = geonames_db['allCountries'].find({}, timeout=False)

    i = 0
    disqualified = 0
    collisions = 0

    seen_names = set()

    numPatt = re.compile('^[0-9]*$')

    for location in res:
        i += 1
        if i % 1000 == 0:
            print "i", i
            print "disqualified", disqualified
            print "collisions", collisions
            print location
            print "\n"

        if 'name' in location and 'population' in location and location['population'] > 0:
            display_name = location['name']
            if 'admin1 code' in location and not numPatt.match(location['admin1 code']):
                display_name += ', ' + location['admin1 code']
            if 'admin2 code' in location and not numPatt.match(location['admin2 code']):
                display_name += ', ' + location['admin2 code']
            if 'admin3 code' in location and not numPatt.match(location['admin3 code']):
                display_name += ', ' + location['admin3 code']
            if 'country' in location:
                display_name += ', ' + location['country']
            elif 'country code' in location:
                display_name += ', ' + location['country code']

            display_name += ' (' + location['geonameid'] + ')'

            if display_name in seen_names:
                collisions += 1
                print "seen already:", display_name
            else:
                seen_names.add(display_name)

            autocomplete = {
                'name': display_name,
                'geonameid': location['geonameid']
            }
            db['locations'].insert(autocomplete)
        else:
            disqualified += 1

    print "Done."
    print "Records seen:", i
    print "Records disqualified:", disqualified
    print "Display name collisions:", collisions

