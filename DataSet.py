import disease_label_table
import numpy as np
from diagnosis.utils import group_by, flatten

label_overrides = {
    '532c9b63f99fe75cf5383521' : ['Gastroenteritis'],
    '532cc391f99fe75cf5389989' : ['Tuberculosis']
}

class DataSet(object):
    """
    A training or test dateset for a classifier
    """
    def __init__(self, feature_extractor, items=None):
        self.feature_extractor = feature_extractor
        self.items = []
        if items:
            for item in items:
                self.append(item)
    def append(self, item):
        if item['_id'] in label_overrides:
            item['labels'] = label_overrides[r['_id']]
        else:
            item['labels'] = [
                disease
                for event in item['meta']['events']
                for disease in event['diseases']
                # TODO: Use disease label table here when it's ready
                if disease is not None and
                    disease_label_table.is_not_human_disease( disease ) and
                    # TODO: We should make multiple classifiers
                    # if we want to also diagnose plant and animal diseases. 
                    not (
                        event.get('species') and
                        len(event.get('species')) > 0 and
                        event.get('species').lower() != "humans"
                    )
            ]
        if len(item['labels']) == 0:
            # There are too many to list:
            # print "Warning: skipping unlabeled (or animal only) item at",\
            #     "http://healthmap.org/ai.php?" + item['name'][:-4]
            return
        return self.items.append(item)
    def __len__(self):
        return len(self.items)
    def get_feature_dicts(self):
        if hasattr(self, '_feature_dicts'):
            return self._feature_dicts
        def get_cleaned_english_content(report):
            translation_dict = report\
                .get('private', {})\
                .get('englishTranslation')
            if translation_dict:
                assert translation_dict.get('error') is None
                assert translation_dict.get('content')
                return translation_dict.get('content')
            else:
                return  report\
                .get('private', {})\
                .get('cleanContent', {})\
                .get('content')
        self._feature_dicts = self.feature_extractor.transform(
            map(get_cleaned_english_content, self.items)
        )
        return self._feature_dicts
    def get_feature_vectors(self):
        """
        Vectorize feature_dicts, filter some out, and add parent labels.
        """
        if hasattr(self, '_feature_vectors'):
            return self._feature_vectors
        features = []
        for feature_vector in self.dict_vectorizer.transform(self.get_feature_dicts()):
            if feature_vector.sum() == 0:
                #print "Warning: all zero feature vector"
                pass
            features.append(feature_vector)
        self._feature_vectors = np.array(features)
        return self._feature_vectors
    def get_labels(self, add_parents=False):
        def get_item_labels(item):
            if add_parents:
                return list(set(
                    item['labels'] +\
                    list(flatten(map(disease_label_table.get_disease_parents, item['labels'])))))
            else:
                return item['labels']
        return map(get_item_labels, self.items)
    def remove_zero_feature_vectors(self):
        props = zip(self.items, self.get_feature_dicts(), self.get_feature_vectors())
        original_items = self.items
        self.items = []
        self._feature_dicts = []
        self._feature_vectors = []
        for item, f_dict, f_vec in props:
            if f_vec.sum() > 0:
                self.items.append(item)
                self._feature_dicts.append(f_dict)
                self._feature_vectors.append(f_vec)
        print "Articles removed because of zero feature vectors:"
        print len(original_items) - len(self.items), '/', len(original_items)
