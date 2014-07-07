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
            self.assertListEqual(extract_counts(example).next()['textOffsets'][0], expected_offset)
            
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
    def test_cumulative(self):
        example = "In total nationwide, 2613 cases of the disease have been reported as of 2 Jul 2014, with 63 deaths"
        actual_count = 2613
        count_obj = next(extract_counts(example), {})
        self.assertEqual(count_obj.get('type'), "caseCount")
        self.assertEqual(count_obj.get('cumulative'), True)
        self.assertEqual(count_obj.get('value'), actual_count)
    def test_cumulative2(self):
        example = "it has already claimed about 455 lives in Guinea"
        actual_count = 455
        count_obj = next(extract_counts(example), {})
        self.assertEqual(count_obj.get('type'), "deathCount")
        self.assertEqual(count_obj.get('cumulative'), True)
        self.assertEqual(count_obj.get('value'), actual_count)
    def test_cumulative3(self):
        example = "there have been a total of 176 cases of human infection with influenza A(H1N5) virus including 63 deaths in Egypt"
        actual_count = 176
        count_obj = next(extract_counts(example), {})
        self.assertEqual(count_obj.get('type'), "caseCount")
        self.assertEqual(count_obj.get('cumulative'), True)
        self.assertEqual(count_obj.get('value'), actual_count)
    def test_value_modifier(self):
        example = "The average number of cases reported annually is 600"
        actual_count = 600
        count_obj = next(extract_counts(example), {})
        self.assertSetEqual(set(count_obj.get('modifiers')), set(["average", "annual"]))
        self.assertEqual(count_obj.get('value'), actual_count)
    def test_duplicates(self):
        example = "Two patients died out of four patients."
        counts = [c['value'] for c in extract_counts(example)]
        self.assertListEqual(counts, [2,4])

class TestCountExtractorAspirations(unittest.TestCase):
    def test_vague(self):
        example = "Hundreds of people have possibly contracted the disease cholera over the past few days"
        actual_count = 200
        count_obj = next(extract_counts(example), {})
        self.assertEqual(count_obj.get('type'), "caseCount")
        self.assertEqual(count_obj.get('aproximate'), True)
        self.assertEqual(count_obj.get('value'), actual_count)
    def test_location_association(self):
        example = "500 new MERS cases that Saudi Arabia has reported in the past 3 months appear to have occurred in hospitals"
        actual_count = 500
        count_obj = next(extract_counts(example), {})
        self.assertEqual(count_obj.get('location'), "Saudi Arabia")
        self.assertEqual(count_obj.get('value'), actual_count)
    def test_time_association(self):
        example = "Since 2001, the median annual number of cases in the U.S. was 60"
        actual_count = 60
        count_obj = next(extract_counts(example), {})
        self.assertEqual(count_obj.get('time'), "2001")
        self.assertEqual(count_obj.get('valueModifier'), "median")
        self.assertEqual(count_obj.get('value'), actual_count)
    def test_misc2(self):
        example = "These 2 new cases bring to 4 the number of people stricken in California this year [2012]."
        count_set = set([count['value'] for count in extract_counts(example)])
        self.assertSetEqual(count_set, set([2,4]))