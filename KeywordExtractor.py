import re

class KeywordExtractor():
    def __init__(self, keywords):
        kw_set = set(map(re.escape, keywords))
        self.kw_re = re.compile('\\b(' + '|'.join(kw_set) + ')\\b', re.I)

    def extract_features(self, text):
        feature_dict = {}
        #TODO: Measure accuracy difference of just using booleans
        #to measure keyword presence rather than counts
        for match in self.kw_re.finditer(text):
            keyword = text[match.start():match.end()].lower()
            feature_dict[keyword] = feature_dict.get(keyword, 0) + 1
        return feature_dict