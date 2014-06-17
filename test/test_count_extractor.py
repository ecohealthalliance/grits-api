import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import unittest
from diagnosis.feature_extractors import extract_counts

class TestCountExtractor(unittest.TestCase):

    def test_verbal_counts(self):
        examples = {
            "it brings the number of cases reported in Jeddah since 27 Mar 2014 to 28" : 28,
            "The number of cases exceeds 30" : 30,
        }
        for example, actual_count in examples.items():
            count_obj = next(extract_counts(example), {})
            self.assertEqual(count_obj.get('value'), actual_count)
    def test_count_offsets(self):
        examples = {
            "The ministry of health reports seventy five new patients were admitted" : "seventy five"
        }
        for example, count_text in examples.items():
            expected_offset = [example.find(count_text), example.find(count_text) + len(count_text)]
            self.assertListEqual(extract_counts(example).next()['textOffsets'], expected_offset)
            
    def test_hospital_counts(self):
        examples = {
            "222 were admitted to hospitals with symptoms of diarrhea" : 222,
            "33 were hospitalized" : 33
        }
        for example, actual_count in examples.items():
            count_obj = next(extract_counts(example), {})
            self.assertEqual(count_obj.get('type'), "hospitalizationCount")
            self.assertEqual(count_obj.get('value'), actual_count)
    def test_written_numbers(self):
        example = "two hundred and twenty two patients were admitted to hospitals"
        actual_count = 222
        count_obj = next(extract_counts(example), {})
        self.assertEqual(count_obj.get('type'), "hospitalizationCount")
        self.assertEqual(count_obj.get('value'), actual_count)
    def test_death_counts(self):
        example = "Nine patients died last week"
        actual_count = 9
        count_obj = next(extract_counts(example), {})
        self.assertEqual(count_obj.get('type'), "deathCount")
        self.assertEqual(count_obj.get('value'), actual_count)
    def test_death_counts_pattern_problem(self):
        example = "Deaths: 2"
        actual_count = 2
        count_obj = next(extract_counts(example), {})
        self.assertEqual(count_obj.get('type'), "deathCount")
        self.assertEqual(count_obj.get('value'), actual_count)
    def test_misc(self):
        example = "1200 children between the ages of 2-5 are afflicted with a mystery illness"
        actual_count = 1200
        count_obj = next(extract_counts(example), {})
        self.assertEqual(count_obj.get('type'), "caseCount")
        self.assertEqual(count_obj.get('value'), actual_count)
    def test_misc2(self):
        example = "These 2 new cases bring to 4 the number of people stricken in California this year [2012]."
        count_set = set([count['value'] for count in extract_counts(example)])
        self.assertSetEqual(count_set, set([2,4]))
