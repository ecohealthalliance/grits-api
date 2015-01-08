import disease_label_table
import numpy as np
from diagnosis.utils import group_by, flatten
import pymongo
import datetime

label_overrides = {
    'http://healthmap.org/ai.php?1097880' : ['Gastroenteritis'],
    'http://healthmap.org/ai.php?1220150' : ['Tuberculosis'],
    'http://healthmap.org/ai.php?2612741' : ['Malaria', 'Diarrhoea', 'Dengue'],
    'http://healthmap.org/ai.php?2845361' : ['Dengue'],
    'http://healthmap.org/ai.php?2884661' : ['Echinococcosis'],
    # Articles to omit have no labels:
    # All the information is in the video
    "http://healthmap.org/ai.php?2960401" : [],
    # This article is actually a travel health notice aggregation page with
    # multiple diseases mentioned.
    # I think it is best to omit it.
    "http://healthmap.org/ai.php?1348711" : [],
    "http://healthmap.org/ai.php?2882489": ['Dengue', 'Chikungunya']
}
# Switch the urls in label overrides to be names in our mongo database.
label_overrides = {
    k.split('?')[1] + '0000' : v
    for k, v in label_overrides.items()
}

class DataSet(object):
    """
    A training or test dateset for a classifier
    """
    def __init__(self, items=None):
        self.items = []
        self.rejected_items = 0
        if items:
            for item in items:
                self.append(item)
    def append(self, item):
        if item['name'] in label_overrides:
            item['labels'] = label_overrides[item['name']]
        else:
            item['labels'] = [
                disease
                for event in item['meta']['events']
                for disease in event['diseases']
                if disease is not None and
                    not disease_label_table.is_not_human_disease( disease ) and
                    # TODO: We should make multiple classifiers
                    # if we want to also diagnose plant and animal diseases. 
                    not (
                        event.get('species') and
                        len(event.get('species')) > 0 and
                        event.get('species').lower() != "humans"
                    )
            ]
        if len(item['labels']) == 0:
            self.rejected_items += 1
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
            features.append(feature_vector)
        self._feature_vectors = np.array(features)
        return self._feature_vectors
    def get_labels(self, add_parents=False):
        def get_item_labels(item):
            if add_parents:
                all_labels = set(item['labels'])
                for label in item['labels']:
                    for l2 in disease_label_table.get_inferred_labels(label):
                        if disease_label_table.is_not_human_disease(l2):
                            continue
                        all_labels.add(l2)
                return list(all_labels)
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

datasets = tuple()
def fetch_datasets():
    global datasets
    if len(datasets) > 0:
        print "Returning cached datasets"
        return datasets
    # The train set is 90% of all data after the first ~7 months of HM data
    # that we have access to.
    # The mixed-test set is the other 10% of the data.
    # The time-offset test set is the first ~6 months.
    # There is a 1 month buffer between the train and test set
    # to avoid overlapping events.
    # We use the first 6 months rather than the last because we keep adding 
    # new data and want this test set to stay the same.
    girder_db = pymongo.Connection('localhost')['girder']
    start_date = datetime.datetime(2013, 1, 8, 0, 9, 12)
    time_offset_test_set = DataSet(girder_db.item.find({
        "meta.date" : {
            "$lte" : start_date + datetime.timedelta(180),
            "$gte" : start_date
        },
        "private.cleanContent.content": { "$ne" : None },
        # There must be no english translation, or the english translation
        # must have content (i.e. no errors occurred when translating).
        "$or" : [
            { "private.englishTranslation": { "$exists" : False } },
            { "private.englishTranslation.content": { "$ne" : None } },
        ],
        "meta.events": { "$ne" : None },
        "private.scrapedData.scraperVersion" : "0.0.3",
        "private.scrapedData.url": { "$exists" : True },
        # This filters out articles that appear to redirect to a different page.
        "$where" : "this.private.scrapedData.sourceUrl.length < this.private.scrapedData.url.length + 12"
    }))
    remaining_reports = girder_db.item.find({
        "meta.date" : {
            "$gt" : start_date + datetime.timedelta(210)
        },
        "private.cleanContent.content": { "$ne" : None },
        "$or" : [
            { "private.englishTranslation": { "$exists" : False } },
            { "private.englishTranslation.content": { "$ne" : None } },
        ],
        "meta.events": { "$ne" : None },
        "private.scrapedData.scraperVersion" : "0.0.3",
        "private.scrapedData.url": { "$exists" : True },
        # This filters out articles that appear to redirect to a different page.
        "$where" : "this.private.scrapedData.sourceUrl.length < this.private.scrapedData.url.length + 12"
    })
    training_set = DataSet()
    mixed_test_set = DataSet()
    
    # If there are too many reports we will run out of memory when training
    # the classifier, so a portion of the reports will not be used if we go
    # over the limit.
    report_limit = 5000
    usable_portion = float(report_limit) / remaining_reports.count()

    for report in remaining_reports:
        # Choose 1/10 articles for the mixed test set
        if int(report['name'][:-4]) % 10 == 9:
            mixed_test_set.append(report)
        else:
            if int(report['name'][:-4]) % 10 < int(usable_portion * 10):
                training_set.append(report)
    
    print "time_offset_test_set size", len(time_offset_test_set), " | rejected items:", time_offset_test_set.rejected_items
    print "mixed_test_set size", len(mixed_test_set), " | rejected items:", mixed_test_set.rejected_items
    print "training_set size", len(training_set), " | rejected items:", training_set.rejected_items
    
    datasets = (
        time_offset_test_set,
        mixed_test_set,
        training_set
    )
    return datasets
