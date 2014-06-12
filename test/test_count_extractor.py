import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import unittest
from diagnosis.feature_extractors import extract_counts

class TestCountExtractor(unittest.TestCase):

    def test_verbal_counts(self):
        examples = {
            "it brings the number of cases reported in Jeddah since 27 Mar 2014 to 28" : 28,
            "The number of cases exceeds 30" : 30,
        }
        for example, count in examples.items():
            self.assertEqual(extract_counts(example).next()['value'], count)
    def test_hospital_counts(self):
        examples = {
            "222 were admitted to hospitals with symptoms of diarrhea" : 222,
            "33 were hospitalized" : 33
        }
        for example, count in examples.items():
            self.assertEqual(extract_counts(example).next()['value'], count)
    def test_written_numbers(self):
        examples = {
            "two hundred and twenty two patients were admitted to hospitals" : 222
        }
        for example, count in examples.items():
            self.assertEqual(extract_counts(example).next()['value'], count)
    def test_death_counts(self):
        examples = {
            "Nine patients died last week" : 9,
            # This is a pattern lib problem, the 2 doesn't get tagged as a CD
            "Deaths: 2" : 2,
        }
        for example, count in examples.items():
            self.assertEqual(extract_counts(example).next()['value'], count)
    def test_misc(self):
        examples = {
            "1200 children between the ages of 2-5 are afflicted with a mystery illness" : 1200,
            "These 2 new cases bring to 4 the number of people stricken in California this year [2012]." : 2,
        }
        for example, count in examples.items():
            self.assertEqual(extract_counts(example).next()['value'], count)
