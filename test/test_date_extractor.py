import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import unittest
from diagnosis.feature_extractors import extract_dates
from datetime import datetime

class TestCountExtractor(unittest.TestCase):

    def test_partials(self):
        dates = extract_dates("Published: 2014-05-30 21:47:55 Nathan will be on vacation from June 19th through Monday June 23rd.")
        self.assertSetEqual(set([d['value'] for d in dates]), set([
            datetime(2014, 5, 30, 21, 47, 55),
            datetime(2014, 6, 19, 0, 0),
            datetime(2014, 6, 23, 0, 0)
        ]))
    
    def test_overlap(self):
        dates = extract_dates("On 30 May 1966 Surveyor 1 was launched.")
        self.assertSetEqual(set([d['value'] for d in dates]), set([
            datetime(1966, 5, 30, 0, 0, 0)
        ]))
