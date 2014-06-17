import numpy as np
import sklearn.pipeline
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import pairwise_distances
from geopy.distance import great_circle
import math
import nltk
import config

def geodistance_with_population(latLngPopA, latLngPopB):
    """
    This geodistance formula measures the distance between
    geographically located circles, with a radius based on
    the population given for a geopoint.
    To determine radius we assume population density of 120/sqmi becasue:
    http://www.wolframalpha.com/input/?i=global+human+population+%2F+global+land+area
    Since the points we're looking at are all cities this is probably a low estimate.
    Then we determine the radius as follows:
    A = pi * r^2
    A = pop / 120
    r = sqrt(pop / (120pi))
    """
    latLngA, latLngB = latLngPopA[0:2], latLngPopB[0:2]
    popA, popB = latLngPopA[2], latLngPopB[2]
    radiusA = math.sqrt(popA / (120 * math.pi))
    radiusB = math.sqrt(popB / (120 * math.pi))
    return max(0, great_circle(latLngA, latLngB).miles - radiusA - radiusB)

def get_ngrams(tokens, maxlen=4):
    """
    Returns all the n-grams in tokens of length less than or equal to maxlen
    """
    if maxlen > 0:
        for idx in xrange(len(tokens) - maxlen + 1):
            yield ' '.join(tokens[idx:idx+maxlen])
        for ngram in get_ngrams(tokens, maxlen - 1):
            yield ngram

def get_ne_chunked_gpes(tokens):
    gpes = []
    tagged_text = nltk.pos_tag(tokens)
    for subtree in nltk.ne_chunk(tagged_text).subtrees():
        if subtree.node == 'GPE':
            gpe = ' '.join([t[0] for t in subtree])
            gpes.append(gpe)
    # TODO: Get GPE offsets
    # TODO: Try searching for ngrams around GPEs
    return gpes
    
def compute_centroid(geoname_objects):
    lats = [gn['latitude'] for gn in geoname_objects]
    longs = [gn['longitude'] for gn in geoname_objects]
    try:
        return {
            'latitude' : sum(lats)/len(lats),
            'longitude' : sum(longs)/len(longs)
        }
    except:
        print "Couldn't compute centroid"
        print geoname_objects

class AnnotatedDict(dict):
    """
    This is a convenience class for adding annotations to dictionaries, eg:
    my_dict = AnnotatedDict({ 'hello' : 'world' })
    my_dict.notes = "This is a great dictionary!"
    """
    pass

class LocationExtractor(sklearn.pipeline.Pipeline):
    omitted_geonames = set([
        'many',
        'may',
        'march',
        'center',
        'as',
        'see',
        'valley',
        'university',
        'about'
    ])
    def __init__(self, geonames_collection=None):
        # I'm using Mongo to import geonames because it is too big to fit in a
        # python dictionary array, and the $in operator provides a fast way to
        # search for all the ngrams in a document.
        if not geonames_collection:
            import pymongo
            db = pymongo.Connection(config.mongo_url)['geonames']
            geonames_collection = db.allCountries
        self.geonames_collection = geonames_collection
        
    def transform_one(self, text):
        name_counts = {}
        # TODO: How well does this handle trailing apostrophies?
        # TODO: Filter locations that are substrings other locations.
        # TODO maybe: Filter locations that based on word frequency probably aren't locations
        # TODO: Filter out locations that based on Part-of-speach clearly aren't names.
        for sent in nltk.sent_tokenize(text):
            tokens = nltk.word_tokenize(sent)
            # I started off using get_ngrams here but had to switch to get_ne_chunked_gpes.
            # Searching for every n-gram in the document can return thousands of geonames.
            # (The lookup is acutally fast but the clustering is really slow).
            # NE chunking allows us to filter out many bad geonames.
            # However, NE chunking is susceptable to false negatives.
            # Stanford NLP might produce better results.
            for possible_geoname in get_ne_chunked_gpes(tokens):
                possible_geoname = possible_geoname.lower()
                if possible_geoname in self.omitted_geonames: continue
                # We will miss some valid names because of this,
                # however it eliminates a lot of bad names like "A" and 10
                if len(possible_geoname) < 3: continue
                name_counts[possible_geoname] = name_counts.get(possible_geoname, 0) + 1
            
        geoname_cursor = self.geonames_collection.find({
            'lemmatized_name' : { '$in' : name_counts.keys() }
        }, {
            # Omit these fields:
            'modification date' : 0,
            'alternatenames': 0,
        })
        
        found_geonames = []
        max_count = 0
        for geoname in geoname_cursor:
            count = name_counts[geoname['lemmatized_name']]
            if count > max_count:
                max_count = count
            # Duplicate the geonames that appear multiple times
            # to increase their weight when clustering them.
            found_geonames += [geoname] * (1 + count / 2)
        
        if len(found_geonames) == 0: return []
        # A clustering algorithm is used with a custom distance metric
        # to remove outliers and group the locations identified.
        found_geopoints = [(g['latitude'], g['longitude']) for g in found_geonames]
        distance_matrix = pairwise_distances(np.c_[np.array(found_geopoints),
                                             [[gn['population']] for gn in found_geonames]],
                                             metric=geodistance_with_population)
        cluster_labels = DBSCAN(
                # The maximum distance between two samples
                # for them to be considered as in the same neighborhood.
                eps=400,
                # The number of samples required to form a cluster is
                # dependent on how many samples we have for the most
                # repeated geoname.
                min_samples=1 + max_count / 2,
                metric='precomputed'
            ).fit(distance_matrix).labels_
        clusters = {k : [] for k in set(cluster_labels)}
        for geoname, cluster_id in zip(found_geonames, cluster_labels):
            if cluster_id < 0:
                #outlier
                continue
            cluster = clusters[cluster_id]
            if geoname not in cluster:
                cluster.append(geoname)
                
        # Keep track of the most likely locations for each name so we can
        # filter out other locations with the same name
        most_likely_locations = {}
        for cluster_id, cluster in clusters.items():
            for location in cluster:
                name = location['name']
                annotated_location = AnnotatedDict(location)
                # +10 is used to prevent cluster size from being the dominating factor.
                annotated_location.liklyhood_score = (10 + len(cluster)) * location['population']
                annotated_location.cluster_id = cluster_id
                if name in most_likely_locations:
                    if most_likely_locations[name].liklyhood_score >= annotated_location.liklyhood_score:
                        continue
                most_likely_locations[name] = annotated_location
        
        clusters = {k:[] for k in clusters.keys()}
        for annotated_location in most_likely_locations.values():
            clusters[annotated_location.cluster_id] += [annotated_location]
        
        if len(clusters) == 0: return []
        min_cluster_size = min(5, max(map(len, clusters.values())))
        return [
            {
                'centroid' : compute_centroid(v),
                'locations' : v
            }
            for k,v in clusters.items()
            if len(v) >= min_cluster_size
        ]
    def transform(self, texts):
        return map(self.transform_one, texts)
