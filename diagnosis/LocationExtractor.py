import sys, csv
import unicodecsv
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import pairwise_distances
from geopy.distance import great_circle
import math
import nltk

def parse_number(num, default):
    try:
        return int(num)
    except ValueError:
        try:
            return float(num)
        except ValueError:
            return default
            
def read_geonames(file_path):
    fieldnames=[
        'geonameid',
        'name',
        'asciiname',
        #TODO: Use this
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
    omitted_geonames = [
        'Many',
        'May',
        'March',
        'Center',
        'As',
        'See',
        'University',
    ]
    with open(file_path, 'rb') as f:
        reader = unicodecsv.DictReader(f,
            fieldnames=fieldnames,
            encoding='utf-8', delimiter='\t', quotechar='\"')
        geoname_roa = []
        for d in reader:
            if d['name'] in omitted_geonames: continue
            d['population'] = parse_number(d['population'], 0)
            d['latitude'] = parse_number(d['latitude'], 0)
            d['longitude'] = parse_number(d['longitude'], 0)
            d['elevation'] = parse_number(d['elevation'], 0)
            d.pop('modification date')
            d.pop('asciiname')
            d.pop('timezone')
            d.pop('alternatenames')
            d.pop('feature class')
            d.pop('dem')
            d.pop('cc2')
            geoname_roa.append(d)
        return geoname_roa

def read_country_names(file_path):
    fieldnames=['ISO',
         'ISO3',
         'ISO-Numeric',
         'fips',
         'Country',
         'Capital',
         'Area(in sq km)',
         'Population',
         'Continent',
         'tld',
         'CurrencyCode',
         'CurrencyName',
         'Phone',
         'Postal Code Format',
         'Postal Code Regex',
         'Languages',
         'geonameid',
         'neighbours',
         'EquivalentFipsCode']
    with open(file_path, 'rb') as f:
        while f.readline().startswith('#'):
            pass
        reader = unicodecsv.DictReader(f,
            fieldnames=fieldnames,
            encoding='utf-8', delimiter='\t', quotechar='\"')
        country_roa = []
        for d in reader:
            d['population'] = parse_number(d['Population'], 0)
            d['name'] = d['Country']
            country_roa.append(d)
        return country_roa

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


def ngrams(li, maxlen):
    """
    Returns all the n-grams in li of length less than or equal to maxlen
    """
    if maxlen > 0:
        for idx in range(len(li) - maxlen):
            yield li[idx:idx+maxlen]
        for ngram in ngrams(li, maxlen - 1):
            yield ngram

def compute_centroid(geoname_objects):
    lats = [gn['latitude'] for gn in geoname_objects]
    longs = [gn['longitude'] for gn in geoname_objects]
    try:
        return {
            'latitude' : sum(lats)/len(lats),
            'longitude' : sum(longs)/len(longs)
        }
    except:
        print lats, longs
class LocationExtractor():
    def __init__(self):
        #Loading geonames data may cause errors without this line:
        csv.field_size_limit(sys.maxsize / 16)

        geoname_roa = read_geonames('geonames/cities1000.txt')
        
        country_index = {}
        for gn in geoname_roa:
            country_index[gn['country code']] = country_index.get(gn['country code'], []) + [gn]
        
        country_lat_longs = {
            country_code : np.mean([[c['latitude'], c['longitude']] for c in cities], axis=0)
            for country_code, cities in country_index.items()
        }
        
        country_name_roa = []
        for r in read_country_names('geonames/countryInfo.txt'):
            if r['ISO'] in country_lat_longs:
                r['latitude'], r['longitude'] = country_lat_longs[r['ISO']]
                country_name_roa.append(r)
            
        self.geoname_index = {}
        for gn in geoname_roa + country_name_roa:
            self.geoname_index[gn['name']] = self.geoname_index.get(gn['name'], []) + [gn]
        
    def transform_one(self, text):
        ngram_counts = {}
        for sent in nltk.sent_tokenize(text):
            tokens = nltk.word_tokenize(sent)
            for ngram in ngrams(tokens, 4):
                # TODO: Filter location that are substrings of NLTK GPEs e.g. York Road?
                ngram_string = ' '.join([unicode(token) for token in ngram])
                ngram_counts[ngram_string] = ngram_counts.get(ngram_string, 0) + 1
        
        found_geonames = []
        max_count = 0
        for ngram, count in sorted(ngram_counts.items(), key=lambda k:k[1]):
            matching_geonames = self.geoname_index.get(ngram)
            if matching_geonames:
                if count > max_count:
                    max_count = count
                for geoname in matching_geonames:
                    # Additional geopoints are created for repeated geonames
                    # to increase their weight when clustering them.
                    found_geonames += [geoname] * (1 + count / 2)
        
        if len(found_geonames) > 0:
            found_geopoints = [(g['latitude'], g['longitude']) for g in found_geonames]
            distance_matrix = pairwise_distances(np.c_[np.array(found_geopoints),
                                                 [[gn['population']] for gn in found_geonames]],
                                                 metric=geodistance_with_population)
            cluster_labels = DBSCAN(
                    #500 miles is the maximum distance between two samples
                    #for them to be considered as in the same neighborhood.
                    eps=500,
                    #min_samples=max(2, len(found_geopoints)/5),
                    #The number of samples required to form a cluster is
                    #dependent on how many samples we have for the most
                    #repeated geoname.
                    min_samples=max_count / 2,
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
            for cluster_id, cluster in clusters.items():
                # If a cluster contains more than one location with a given name
                # the article probably only refers to one of them, so guess
                # the one with the greatest population
                most_populous_locations = {}
                for location in cluster:
                    if location['name'] in most_populous_locations:
                        if most_populous_locations[location['name']]['population'] >= location['population']:
                            continue
                    most_populous_locations[location['name']] = location
                clusters[cluster_id] = most_populous_locations.values()
            if len(clusters) > 0:
                min_cluster_size = min(5, max(map(len, clusters.values())))
                return [
                    {
                        'centroid' : compute_centroid(v),
                        'locations' : v
                    }
                    for k,v in clusters.items()
                    if len(v) >= min_cluster_size
                ]
        return []
    def transform(self, texts):
        return map(self.transform_one, texts)