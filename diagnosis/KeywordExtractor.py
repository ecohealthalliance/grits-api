import re

class KeywordExtractor():
    """
    Does case insensitive matching and all returned keywords are lowercase.
    Keyword set is *not* culled during the fit operation.
    """
    def __init__(self, keywords):
        self.keywords = set([re.escape(kw.lower()) for kw in keywords])
        self.kw_re = re.compile('\\b(' + '|'.join(self.keywords) + ')\\b', re.I)
    def fit(self, X, y):
        pass
    def transform_one(self, text):
        feature_dict = {}
        for match in self.kw_re.finditer(text):
            keyword = text[match.start():match.end()].lower()
            feature_dict[keyword] = feature_dict.get(keyword, 0) + 1
        return feature_dict
    def transform(self, texts):
        return map(self.transform_one, texts)
        
class LinkedKeywordAdder():
    def __init__(self, keyword_links):
        self.keyword_links = keyword_links
    def fit(self, X, y):
        pass
    def transform_one(self, keyword_counts):
        out_dict = keyword_counts.copy()
        for k,v in keyword_counts.items():
            linked_keywords = self.keyword_links.get(k, [])
            for k2 in linked_keywords:
                out_dict[k2] = out_dict.get(k2, 0) + (float(v) / len(linked_keywords))
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
