import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import unittest
import corpora
from diagnosis.LocationExtractor import LocationExtractor
from corpora.iterate_resources import process_resource_file
from corpora.process_resources import attach_translations, process_resource

def get_processed_resource(file):
    resource = process_resource_file(os.path.join('../corpora', file))
    attach_translations([resource])
    return process_resource(resource)

class TestLocationExtractor(unittest.TestCase):

    def setUp(self):
        self.location_extractor = LocationExtractor()

    def test_people_names(self):
        """
        This tests an article that has a number of people names that can be easily
        mistken for locations.
        """
        resource = get_processed_resource('healthmap/devtest/53304886f99fe75cf5392398.md')
        assert resource['translated']
        text = resource['cleanContent']
        found_names = set()
        for cluster in self.location_extractor.transform([text])[0]:
            found_names |= set([l['name'] for l in cluster['locations']])
        self.assertSetEqual(found_names, set(['Luque', 'Villa Elisa']))

    def test_misc(self):
        resource = get_processed_resource('healthmap/devtest/532ccf7ff99fe75cf538b747.md')
        text = resource['cleanContent']
        found_names = set()
        for cluster in self.location_extractor.transform([text])[0]:
            found_names |= set([l['name'] for l in cluster['locations']])
        self.assertSetEqual(found_names, set(['Yosemite', 'Canada']))

# To be added:
#http://promedmail.org/direct.php?id=2363058
#location information totally incorrect- should be in Africa, but picked up all US Locations that are also common words: Union, Scott, Enigma, Henry. Easy locations such as Africa and Sudan not getting picked up, as well as more challenging village/region names

