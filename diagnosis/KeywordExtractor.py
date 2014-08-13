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
from sklearn.pipeline import FeatureUnion
from scipy.sparse import hstack


class KeywordExtractor():
    """
    Does case insensitive matching and all returned keywords are lowercase.
    Keyword set is *not* culled during the fit operation.
    """
    def __init__(self, keyword_array):
        case_sensitive = set()
        not_case_sensitive = set()
        for kw_obj in keyword_array:
            keyword = kw_obj['keyword']
            if kw_obj['case_sensitive']:
                case_sensitive.add(keyword)
            else:
                not_case_sensitive.add(keyword.lower())
        
        self.case_insensitive_vectorizer = CountVectorizer(
            vocabulary=not_case_sensitive,
            ngram_range=(1, 4)
        )
        self.case_sensitive_vectorizer = CountVectorizer(
            vocabulary=case_sensitive,
            ngram_range=(1, 1),
            lowercase=False
        )
    def fit(self, X, y):
        pass
    def transform_with_vectorizer(self, vectorizer, texts):
        mat = vectorizer.transform(texts)
        vocab = vectorizer.get_feature_names()
        out_dicts = []
        for r in range(mat.shape[0]):
            out_dict = {}
            for c in mat[r].nonzero()[1]:
                out_dict[vocab[c]] = mat[r,c]
            out_dicts.append(out_dict)
        return out_dicts
    def transform(self, texts):
        out_dicts = self.transform_with_vectorizer(
            self.case_insensitive_vectorizer,
            texts
        )
        # out_dict_updates = self.transform_with_vectorizer(
        #     self.case_sensitive_vectorizer,
        #     texts
        # )
        # for d, upd in zip(out_dicts, out_dict_updates):
        #     d.update(upd)
        return out_dicts

class KeywordExtractorUnion():
    """
    I wanted to combine the vectors rather than the dicts but I kept
    getting errors when using scipy's hstack on large vectors.
    """
    def __init__(self, keywords, case_sensitive_keywords):
        assert len(keywords) > 0 and len(case_sensitive_keywords) > 0
        self.vectorizer = FeatureUnion([
            (
                'case_insensitive',
                CountVectorizer(
                    vocabulary=keywords,
                    ngram_range=(1, 4)
                ),
            ),
            (
                'case_sensitive',
                CountVectorizer(
                    vocabulary=case_sensitive_keywords,
                    ngram_range=(1, 1),
                    lowercase=False
                )
            )
        ], n_jobs=2)
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
    def __init__(self, keyword_links, weight=1):
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

class SynonymReducer():
    """
    Reduces multiple words to a single feature.
    Possibly helpful because having lots of syns for a word would cause it to
    affect the score more.
    """
    def __init__(self, keyword_array):
        self.kw_to_syn_group = kw_to_syn_group
    def fit(self, X, y):
        pass
    def transform_one(self, keyword_counts):
        out_dict = keyword_counts.copy()
        for k,v in keyword_counts.items():
            k2 = self.kw_to_syn_group.get(k, k)
            out_dict[k2] = out_dict.get(k2, 0) + 1
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

class ProcessProperty():
    def __init__(self, stage, inprop, outprop):
        self.stage = stage
        self.inprop = inprop
        self.outprop = outprop
    def fit(self, X_docs, y):
        X = [doc[self.inprop] for doc in X_docs]
        self.stage(X, y)
    def transform(self, X_docs):
        X = [doc[self.inprop] for doc in X_docs]
        for x in self.stage(X, y):
            X_docs[self.outprop] = x
        return X_docs
