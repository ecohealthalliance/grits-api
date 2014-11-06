#!/usr/bin/env python
"""
Load mongo with autocomplete data for the keywords for annie annotation and
potentially autocompletion.
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
        ('hosts', ['wordnet/hosts']),
        ('pathogens', ['wordnet/pathogens', 'biocaster/pathogens']),
        ('modes', ['pm/mode of transmission', 'doid/transmitted_by'])
    ]

    for category, labels in category_labels:
        collection = db[category]

        names_set = set()
        for label in labels:
            names_set = names_set.union(keyword_sets[label])

        insert_set(names_set, collection)
