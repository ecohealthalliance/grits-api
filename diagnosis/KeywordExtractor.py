import re

def partition(iterable, batch_size=500):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    yield batch

from sklearn.feature_extraction.text import CountVectorizer

class KeywordExtractor():
    """
    Does case insensitive matching and all returned keywords are lowercase.
    Keyword set is *not* culled during the fit operation.
    """
    def __init__(self, keywords):
        self.vectorizer = CountVectorizer(vocabulary=keywords, ngram_range=(1, 4))
    def fit(self, X, y):
        pass
    def transform(self, texts):
        mat = self.vectorizer.transform(texts)
        vocab = self.vectorizer.get_feature_names()
        out_dicts = []
        for r in range(mat.shape[0]):
            out_dict = {}
            for c in mat[r].nonzero()[1]:
                out_dict[vocab[c]] = mat[r,c]
            out_dicts.append(out_dict)
        return out_dicts

import pattern.search, pattern.en
class PatternExtractor():
    """
    Too slow
    """
    def __init__(self, patterns):
        self.patterns = set(patterns)
        
    def fit(self, X, y):
        pass
    def transform_one(self, text):
        feature_dict = {}
        tree = pattern.en.parsetree(text)
        for p in self.patterns:
            for match in pattern.search.search(p, tree):
                feature_dict[p] = feature_dict.get(p, 0) + 1
        return feature_dict
    def transform(self, texts):
        return map(self.transform_one, texts)

class LinkedKeywordAdder():
    def __init__(self, keyword_links, weight=.4):
        self.weight = weight
        self.keyword_links = keyword_links
    def fit(self, X, y):
        pass
    def transform_one(self, keyword_counts):
        out_dict = keyword_counts.copy()
        for k,v in keyword_counts.items():
            linked_keywords = self.keyword_links.get(k, [])
            for k2 in linked_keywords:
                out_dict[k2] = out_dict.get(k2, 0) + (float(v) * self.weight)
        return out_dict
    def transform(self, keyword_count_dicts):
        return map(self.transform_one, keyword_count_dicts)

class LimitCounts():
    def __init__(self, max_count=1):
        self.max_count = max_count
    def fit(self, X, y):
        pass
    def transform_one(self, in_dict):
        return { k : min(self.max_count, v) for k,v in in_dict.items() }
    def transform(self, keyword_count_dicts):
        return map(self.transform_one, keyword_count_dicts)

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer as Summarizer
#from sumy.summarizers.lex_rank import LexRankSummarizer as Summarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words

class Summarize():
    def __init__(self, num_sentences=10):
        self.num_sentences = num_sentences
        stemmer = Stemmer("english")
        self.summarizer = Summarizer(stemmer)
        self.summarizer.stop_words = get_stop_words("english")
    def fit(self, X, y):
        pass
    def transform_one(self, text):
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        try:
            return ' '.join([unicode(s) for s in self.summarizer(parser.document, self.num_sentences)])
        except ZeroDivisionError as e:
            return text
    def transform(self, texts):
        return map(self.transform_one, texts)

class RemoveSentences():
    def __init__(self, stop_words=None):
        if not stop_words:
            stop_words = ['not']
        self.regex = re.compile(r'(?<=[\.\n\A]).*?\b(' +\
            r'|'.join(map(re.escape, stop_words)) +\
            r')\b.*?[\.\n]', re.I | re.DOTALL)
    def fit(self, X, y):
        pass
    def transform_one(self, text):
        return self.regex.subn('', text)[0]
    def transform(self, texts):
        return map(self.transform_one, texts)
