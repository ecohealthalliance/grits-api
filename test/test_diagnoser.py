import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import unittest
import pickle
from diagnosis.Diagnoser import Diagnoser

class TestDiagnoser(unittest.TestCase):
    def setUp(self):
        with open('../classifier.p') as f:
            my_classifier = pickle.load(f)
        with open('../dict_vectorizer.p') as f:
            my_dict_vectorizer = pickle.load(f)
        with open('../keyword_array.p') as f:
            keyword_array = pickle.load(f)
        self.my_diagnoser = Diagnoser(
            my_classifier,
            my_dict_vectorizer,
            keyword_array=keyword_array,
            cutoff_ratio=.7
        )
        
    def test_duplicate_parents(self):
        diagnosis = self.my_diagnoser.diagnose("Hepatitis B, Hepatitis C, and Hepatitis D and Hepatitis E")
        diseases = [d['name'] for d in diagnosis['diseases']]
        self.assertEqual(len(diseases), len(set(diseases)))