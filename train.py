# load the training/validation resources and ontology data from AWS
from boto.s3.connection import S3Connection, Location
import datetime
import os
import pickle
import config
import diagnosis
from diagnosis.KeywordExtractor import *
from diagnosis.Diagnoser import Diagnoser
from diagnosis.Diagnoser import disease_to_parent
from diagnosis.Diagnoser import get_disease_parents
import numpy as np
import re
import sklearn
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction import DictVectorizer
from sklearn.multiclass import OneVsRestClassifier
from sklearn.linear_model import LogisticRegression
from diagnosis.utils import group_by, flatten
import warnings
import pymongo

def get_pickle(filename):
    """
    Download the pickle from the AWS bucket if it's stale,
    save it in the workspace, and return the loaded data.
    """
    try:
        conn = S3Connection(config.aws_access_key, config.aws_secret_key)
        bucket = conn.get_bucket('classifier-data')
        k = bucket.get_key(filename)
        from dateutil import parser
        from tzlocal import get_localzone
        tz = get_localzone()
        if os.path.exists(filename):
            local_copy_time = datetime.datetime.fromtimestamp(
                os.path.getctime(filename)
            )
        else:
            # This datetime that should always be before the remote copy timestamp.
            # However, if it is too close to datetime min it can't be
            # localized in some timezones.
            local_copy_time = datetime.datetime(1,2,3)
        remote_copy_time = parser.parse(k.last_modified)
        if tz.localize(local_copy_time) < remote_copy_time:
            print "Downloading", filename
            k.get_contents_to_filename(filename)
    except:
        print "Could not download fresh pickle: " + filename
    with open(filename) as f:
        result = pickle.load(f)
        print filename, "loaded"
        return result

label_overrides = {
    '532c9b63f99fe75cf5383521' : ['Gastroenteritis'],
    '532cc391f99fe75cf5389989' : ['Tuberculosis']
}

labels_to_omit = [
    'Not Yet Classified',
    'Undiagnosed',
    # Maybe Other Human/Animal/Plant Disease labels could be turned into categories?
    # The problem is we don't know which are negative examples of them.
    'Other Human Disease',
    'Other Animal Disease',
    'Other Plant Disease',
    #Pathogen labels:
    'Food-related toxin',
    'Free Living Amoeba',
    'Pests',
    'Bite',
    'E. coli',
    'Algae',
    #Labels I'm not sure what to make of:
    'Vaccine Complication',
    'Environmental',
    'Conflict',
    'Animal Die-off',
    'Poisoning',
    'Paralytic Shellfish Poisoning',
    'Cold',
]
# Previously I had ommited 'Amoeba' because it is a type of organism rather than
# a disease. However, now that I've investigated some of the articles labeled
# with it, I think it should be included because it labels reports about
# amoeba caused diseases that aren't covered by another label. 
# E.g. brain eating amoeba causes "primary amoebic meningoencephalitis" 
# (If we did have articles labeled this way, excluding the amoeba label
# would help since inconsistent labels confuse the classifier).

# Should we omit these?:
# Foodborne Illness
# Parotitis
# Hospital-Related Infection

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
                    disease not in labels_to_omit and
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
            translation = report\
                .get('private', {})\
                .get('englishTranslation', {})\
                .get('content')
            if translation:
                return translation
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
                    list(flatten(map(get_disease_parents, item['labels'])))))
            else:
                return item['labels']
        return map(get_item_labels, self.items)
    def remove_zero_feature_vectors(self):
        props = zip(self.items, self.get_feature_dicts(), self.get_feature_vectors())
        self.items = []
        self._feature_dicts = []
        self._feature_vectors = []
        for item, f_dict, f_vec in props:
            if f_vec.sum() > 0:
                self.items.append(item)
                self._feature_dicts.append(f_dict)
                self._feature_vectors.append(f_vec)
        # TODO:
        # print "articles we could extract keywords from:"
        # print len(resources_validation), '/', len(validation_set)
def train(debug):
    keywords = get_pickle('ontologies-0.1.3.p')
    
    categories = set([
        'hm/disease',
        'biocaster/pathogens',
        'biocaster/diseases',
        'biocaster/symptoms',
        'symp/symptoms',
        'eha/symptom',
        'eha/mode of transmission',
        'eha/environmental factors',
        'eha/vector',
        'eha/occupation',
        'eha/control measures',
        'eha/description of infected',
        'eha/disease category',
        'eha/host',
        'eha/host use',
        'eha/symptom',
        'eha/disease',
        'eha/location', 
        'eha/transmission',
        'eha/zoonotic type',
        'eha/risk',
        'wordnet/season',
        'wordnet/climate',
        'wordnet/pathogens',
        'wordnet/hosts',
        'wordnet/mod/severe',
        'wordnet/mod/painful',
        'wordnet/mod/large',
        'wordnet/mod/rare',
        'doid/has_symptom',
        'doid/symptoms',
        'doid/transmitted_by',
        'doid/located_in',
        'doid/diseases',
        'doid/results_in',
        'doid/has_material_basis_in',
        'usgs/terrain'
    ])

    keyword_array = [
        keyword_obj for keyword_obj in keywords
        if keyword_obj['category'] in categories
    ]
    
    usused_keyword_cats = set([
        keyword_obj['category'] for keyword_obj in keywords
        if keyword_obj['category'] not in categories
    ])
    if len(usused_keyword_cats) > 0:
        print "Unused keyword categories:"
        print usused_keyword_cats
    
    # Keyword Extraction
    feature_extractor = Pipeline([
        ('kwext', KeywordExtractor(keyword_array)),
        ('link', LinkedKeywordAdder(keyword_array)),
        ('limit', LimitCounts(1)),
    ])
    
    # The train set is 90% of all data after the first ~7 months of HM data
    # (everything before August 30).
    # The mixed-test set is the other 10% of the data.
    # The time-offset test set is the first ~6 months.
    # There is a 1 month buffer between the train and test set
    # to avoid overlapping events.
    # We use the first 6 months rather than the last because we keep adding 
    # new data and want this test set to stay the same.
    girder_db = pymongo.Connection('localhost')['girder']
    time_offset_test_set = DataSet(feature_extractor, girder_db.item.find({
        "created" : {
            "$lte" : datetime.datetime(2012, 8, 30)
        },
        "private.cleanContent.content": { "$ne" : None },
        "meta.events": { "$ne" : None }
    }))
    remaining_reports = girder_db.item.find({
        "created" : {
            "$gt" : datetime.datetime(2012, 9, 30)
        },
        "private.cleanContent.content": { "$ne" : None },
        "meta.events": { "$ne" : None }
    })
    training_set = DataSet(feature_extractor)
    mixed_test_set = DataSet(feature_extractor)
    for report in remaining_reports:
        # Choose 1/10 articles for the mixed test set
        if int(report['name'][:-4]) % 10 == 1:
            mixed_test_set.append(report)
        else:
            # We have to leave some reports out to avoid memory errors
            if int(report['name'][:-4]) % 10 < 7: continue
            training_set.append(report)
    
    print "time_offset_test_set size", len(time_offset_test_set)
    print "mixed_test_set size", len(mixed_test_set)
    print "training_set size", len(training_set)
    
    #If we get sparse rows working with the classifier this might yeild some
    #performance improvments.
    my_dict_vectorizer = DictVectorizer(sparse=False).fit(training_set.get_feature_dicts())
    print 'Found keywords:', len(my_dict_vectorizer.vocabulary_)
    print "Keywords in the validation set that aren't in the training set:"
    print  (
        set(DictVectorizer(sparse=False).fit(
            mixed_test_set.get_feature_dicts()).vocabulary_
        ) -
        set(my_dict_vectorizer.vocabulary_)
    )
    time_offset_test_set.dict_vectorizer = \
    mixed_test_set.dict_vectorizer = \
    training_set.dict_vectorizer = my_dict_vectorizer

    time_offset_test_set.remove_zero_feature_vectors()
    mixed_test_set.remove_zero_feature_vectors()
    training_set.remove_zero_feature_vectors()

    print """
    Articles in the test sets that we are sure to miss
    because we have no training data for their labels:
    """
    validation_label_set = set(
        flatten(
            time_offset_test_set.get_labels() + mixed_test_set.get_labels(),
            1
        )
    )
    not_in_train = [
        label for label in validation_label_set
        if (label not in flatten(training_set.get_labels(), 1))
    ]
    print len(not_in_train),'/',len(validation_label_set)
    print set(not_in_train)

    my_classifier = OneVsRestClassifier(LogisticRegression(
        # When fit intercept is False the classifier predicts nothing when
        # all the features are zero.
        # On one hand, we can guess the article is most likely to be dengue or
        # another common disease and still occassionally be right,
        # and having a intercept offset could allow us
        # to create a model that is a tighter fit.
        # On one hand, predictions based off of nothing might puzzle users.
        # fit_intercept=False,
        # l1 penalty will produce sparser coefficients.
        # it seems to perform worse,
        # but the classifications will be easier to inspect,
        # and we might be able to avoid some overfitting based on weak
        # correlations that turn out to be false.
        # penalty='l1',
        # Using class weighting we might be able to avoid overpredicting
        # the more common labels.
        # However, auto weighting has only hurt our mico f-scores so far.
        # class_weight='auto',
    ), n_jobs=-1)
    
    # Parent labels are not added to the training data because we seem to do
    # better by adding them after the classification.
    # This may be due to the parent classification having such a
    # high confidence that the child labels are pushed below the cutoff.
    my_classifier.fit(
        np.array(training_set.get_feature_vectors()),
        np.array(training_set.get_labels()))
    
    # Pickle everything that will be needed for classification:
    with open('classifier.p', 'wb') as f:
        pickle.dump(my_classifier, f)
    with open('dict_vectorizer.p', 'wb') as f:
        pickle.dump(my_dict_vectorizer, f)
    with open('keyword_array.p', 'wb') as f:
        pickle.dump(keyword_array, f)
    # Reload variables from pickles to test them:
    with open('classifier.p') as f:
        my_classifier = pickle.load(f)
    with open('dict_vectorizer.p') as f:
        my_dict_vectorizer = pickle.load(f)
    with open('keyword_array.p') as f:
        keyword_array = pickle.load(f)
    
    my_diagnoser = Diagnoser(
        my_classifier,
        my_dict_vectorizer,
        keyword_array=keyword_array,
        cutoff_ratio=.7
    )
    with warnings.catch_warnings():
        # The updated version of scikit will spam warnings here.
        warnings.simplefilter("ignore")
        training_predictions = [
            tuple([
                my_diagnoser.classifier.classes_[i]
                for i, p in my_diagnoser.best_guess(X)
            ])
            for X in training_set.get_feature_vectors()
        ]
        print ("Training set (macro avg):\n"
            "precision: %s recall: %s f-score: %s") %\
            sklearn.metrics.precision_recall_fscore_support(
                map(tuple, training_set.get_labels(add_parents=True)),
                training_predictions,
                average='macro'
            )[0:3]
        for data_set, label, print_label_breakdown in [
            #(time_offset_test_set, "Time offset set", True),
            (mixed_test_set, "Mixed test set", False)
        ]:
            predictions = [
                tuple([
                    my_diagnoser.classifier.classes_[i]
                    for i, p in my_diagnoser.best_guess(X)
                ])
                for X in data_set.get_feature_vectors()
            ]
            print label
            # I've noticed that the macro f-score is not the harmonic mean of 
            # the percision and recall. Perhaps this could be a result of the 
            # macro f-score being computed as an average of f-scores.
            # Furthermore, the macro f-scrore can be smaller than the precision 
            # and recall which seems like it shouldn't be possible.
            print predictions[:5]
            print ("Validation set (macro avg):\n"
                "precision: %s recall: %s f-score: %s") %\
                sklearn.metrics.precision_recall_fscore_support(
                    data_set.get_labels(add_parents=True),
                    predictions,
                    average='macro')[0:3]
            print ("Validation set (micro avg):\n"
                "precision: %s recall: %s f-score: %s") %\
                sklearn.metrics.precision_recall_fscore_support(
                    data_set.get_labels(add_parents=True),
                    predictions,
                    average='micro')[0:3]
            
            if print_label_breakdown:
                print "Which classes are we performing poorly on?"
                labels = sorted(
                    list(set(flatten(data_set.get_labels(add_parents=True))) |\
                    set(flatten(predictions)))
                )
                prfs = sklearn.metrics.precision_recall_fscore_support(
                    data_set.get_labels(add_parents=True),
                    predictions,
                    labels=labels
                )
                for cl,p,r,f,s in sorted(zip(labels, *prfs), key=lambda k:k[3]):
                    print cl
                    print "precision:",p,"recall",r,"F-score:",f,"support:",s

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-debug', action='store_true')
    args = parser.parse_args()
    train(args.debug)
