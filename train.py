# load the training/validation resources and ontology data from AWS
from boto.s3.connection import S3Connection, Location
import datetime
import os
import pickle
import config
import diagnosis
from diagnosis.KeywordExtractor import *
from diagnosis.Diagnoser import Diagnoser, get_disease_parents
from diagnosis.Diagnoser import disease_to_parent
import numpy as np
import re
import sklearn
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction import DictVectorizer
from sklearn.multiclass import OneVsRestClassifier
from sklearn.linear_model import LogisticRegression
from diagnosis.utils import group_by, flatten, resource_url

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
    # Foot and Mouth disease rarely affects humans.
    # This sounds like it should be HFM
    '53303a44f99fe75cf5390a56' : 'Hand, Foot and Mouth Disease',
    '532c9b63f99fe75cf5383521' : 'Gastroenteritis',
    '532cc391f99fe75cf5389989' : 'Tuberculosis'
}

labels_to_omit = [
    'Not Yet Classified',
    'Undiagnosed',
    # Maybe Other Human/Animal/Plant Disease labels could be turned into categories?
    # The problem is we don't know which are negative examples of them.
    'Other Human Disease',
    'Other Animal Disease',
    'Other Plant Disease',
    # Pathogen labels:
    # These could be replaced with the diseases they cause
    'Food-related toxin',
    'Free Living Amoeba',
    'Pests',
    'Bite',
    'E. coli',
    'Algae',
    'Amoeba',
    # Labels I'm not sure what to make of:
    'Vaccine Complication',
    'Environmental',
    'Conflict',
    'Animal Die-off',
    'Poisoning',
    'Paralytic Shellfish Poisoning',
    'Cold',
]
#Parotitis is more of a symptom than a disease

def get_features_and_classifications(
    feature_dicts,
    my_dict_vectorizer,
    resources,
    disease_to_parent_map
):
    """
    Vectorize feature_dicts, filter some out, and add parent labels.
    """
    features = []
    out_feature_dicts = []
    classifications = []
    resources_used = []
    for feature_dict, feature_vector, r in zip(
        feature_dicts,
        my_dict_vectorizer.transform(feature_dicts),
        resources
    ):
        if feature_vector.sum() == 0:
            #Skip all zero features
            continue
        if r['meta']['disease'] in labels_to_omit:
            continue
        if r['_id'] in label_overrides:
            diseases = [label_overrides[r['_id']]]
        else:
            diseases = [r['meta']['disease']]
        while diseases[-1] in disease_to_parent_map:
            diseases.append(disease_to_parent_map[diseases[-1]])
        features.append(feature_vector)
        out_feature_dicts.append(feature_dict)
        classifications.append(diseases)
        resources_used.append(r)
    return np.array(features), out_feature_dicts, np.array(classifications), resources_used


def prepare_classifier(debug):
    training_set = get_pickle('training.p')#[:100]
    validation_set = get_pickle('validation.p')#[:200]
    keywords = get_pickle('ontologies-0.1.1.p')
    
    categories = set([
        'hm/disease',
        'eha/symptom',
        'eha/mode of transmission',
        'eha/environmental factors',
        'eha/vector',
        'eha/occupation',
        'eha/control measures',
        'eha/description of infected',
        'eha/disease category',
        'eha/host use',
        'eha/symptom',
        'eha/zoonotic type',
        'eha/risk',
        'biocaster/symptoms',
        'wordnet/season',
        'wordnet/climate',
        'wordnet/pathogens',
        'wordnet/hosts',
        'biocaster/pathogens',
        'biocaster/diseases',
        'symp/symptoms',
        'doid/has_symptom',
        'doid/transmitted_by',
        'doid/located_in',
        'wordnet/mod/severe',
        'wordnet/mod/painful',
        'wordnet/mod/large',
        'doid/diseases',
        'eha/disease'
    ])

    keyword_array = [
        keyword_obj for keyword_obj in keywords
        if keyword_obj['category'] in categories
    ]
    
    # Keyword Extraction
    extract_features = Pipeline([
        ('kwext', KeywordExtractor(keyword_array)),
        ('link', LinkedKeywordAdder(keyword_array)),
        ('limit', LimitCounts(1)),
    ])
    train_feature_dicts = extract_features.transform([
        r['cleanContent'] for r in training_set
    ])
    validation_feature_dicts = extract_features.transform([
        r['cleanContent'] for r in validation_set
    ])
    #If we get sparse rows working with the classifier this might yeild some
    #performance improvments.
    my_dict_vectorizer = DictVectorizer(sparse=False).fit(train_feature_dicts)
    print 'Found keywords:', len(my_dict_vectorizer.vocabulary_)
    print "Keywords in the validation set that aren't in the training set:"
    print  (
        set(DictVectorizer(sparse=False).fit(
            validation_feature_dicts).vocabulary_
        ) -
        set(my_dict_vectorizer.vocabulary_)
    )

    (
        feature_mat_train,
        filtered_train_feature_dicts,
        labels_train,
        resources_train
    ) = get_features_and_classifications(
        train_feature_dicts,
        my_dict_vectorizer,
        training_set,
        {}
    )
    
    (
        feature_mat_validation,
        filtered_validation_feature_dicts,
        labels_validation,
        resources_validation
    ) = get_features_and_classifications(
        validation_feature_dicts,
        my_dict_vectorizer,
        validation_set,
        disease_to_parent
    )
    
    print "articles we could extract keywords from:"
    print len(resources_validation), '/', len(validation_set)
    
    print """
    Articles in the validation set that we are sure to miss
    because we have no training data for their labels:
    """
    
    not_in_train = [
        y for y in flatten(labels_validation, 1)
        if (y not in flatten(labels_train, 1))
    ]
    print len(not_in_train),'/',len(labels_validation)
    print not_in_train
    
    keyword_to_hm_label = {}
    for kw_obj in keyword_array:
        label = kw_obj['synset_object'].get('hm_label')
        if label and label not in labels_to_omit:
            keyword_to_hm_label[kw_obj['keyword'].lower()] = label
            # TODO:
            # Some keywords are used for multiple HM labels
            # e.g. Rubella is a keyword for Rubella and Measles
            # (This comes from a synonym relationship in the biocaster ontology.
            # I believe it may be technically incorrect, but a common usage.) 
            # To mitigate this problem, we could choose the keyword
            # with the shortest lev distance to the label.
    healthmap_labels_found = []
    for d in filtered_validation_feature_dicts:
        # best_label = None
        # best_score = 0
        # for k, score in d.items():
        #     if score > best_score:
        #         hm_label = keyword_to_hm_label.get(k.lower())
        #         if hm_label:
        #             best_label = hm_label
        #             best_score = score
        # if best_label:
        #     healthmap_labels_found.append(
        #         get_disease_parents(best_label) + [best_label]
        #     )
        # else:
        #     healthmap_labels_found.append([])
        doc_hm_label_set = set()
        for k, score in d.items():
            hm_label = keyword_to_hm_label.get(k.lower())
            if hm_label:
                doc_hm_label_set |= set(get_disease_parents(hm_label) + [hm_label])
        healthmap_labels_found.append(list(doc_hm_label_set))
    print 'Articles with HM labels: ',\
        len([k for k in healthmap_labels_found if len(k) > 0]), '/',\
        len(healthmap_labels_found)
    # Print out some of the healthmap labels
    if debug:
        for l, h, r, fvft in zip(
            labels_validation,
            healthmap_labels_found,
            resources_validation,
            filtered_validation_feature_dicts
        )[-20:]:
            if r['_id'] == '53304873f99fe75cf5392377':
                print r
                print fvft
            print l,h,resource_url(r)
    
    (
        feature_mat_validation,
        labels_validation,
        healthmap_labels_found
    ) = zip(*[
        (f_array, label, hm_label_set)
        for f_array, label, hm_label_set in zip(
            feature_mat_validation,
            labels_validation,
            healthmap_labels_found
        )
        #if len(hm_label_set) > 0
    ])
    
    train(
        feature_mat_train,
        labels_train,
        feature_mat_validation,
        labels_validation,
        healthmap_labels_found,
        my_dict_vectorizer,
        keyword_array,
        debug
    )

def train(
    feature_mat_train,
    labels_train,
    feature_mat_validation,
    labels_validation,
    healthmap_labels_found,
    my_dict_vectorizer,
    keyword_array,
    debug
):
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
    
    my_classifier.fit(feature_mat_train, labels_train)
    
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
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        training_predictions = [
            tuple([
                my_diagnoser.classifier.classes_[i]
                for i, p in my_diagnoser.best_guess(X)
            ])
            for X in feature_mat_train
        ]
        print "Training set (macro):\nprecision: %s recall: %s f-score: %s" %\
            sklearn.metrics.precision_recall_fscore_support(
                map(tuple, labels_train),
                training_predictions,
                average='macro'
            )[0:3]
        
        predictions = [
            tuple([
                my_diagnoser.classifier.classes_[i]
                for i, p in my_diagnoser.best_guess(X)
            ])
            for X in feature_mat_validation
        ]
    # I've noticed that the macro f-score is not the harmonic mean of the percision
    # and recall. Perhaps this could be a result of the macro f-score being computed 
    # as an average of f-scores.
    # Furthermore, the macro f-scrore can be smaller than the precision and
    # recall which seems like it shouldn't be possible.
    print "Validation set (macro):\nprecision: %s recall: %s f-score: %s" %\
        sklearn.metrics.precision_recall_fscore_support(
            labels_validation,
            predictions,
            average='macro')[0:3]
    print "Validation set [HM] (macro):\nprecision: %s recall: %s f-score: %s" %\
        sklearn.metrics.precision_recall_fscore_support(
            labels_validation,
            healthmap_labels_found,
            average='macro')[0:3]
    print "Validation set (micro):\nprecision: %s recall: %s f-score: %s" %\
        sklearn.metrics.precision_recall_fscore_support(
            labels_validation,
            predictions,
            average='micro')[0:3]
    print "Validation set [HM] (micro):\nprecision: %s recall: %s f-score: %s" %\
        sklearn.metrics.precision_recall_fscore_support(
            labels_validation,
            healthmap_labels_found,
            average='micro')[0:3]
    # for l, p, r in zip(labels_validation[:100], predictions[:100], validation_set[:100]):
    #     print l,p,resource_url(r)
    
    if debug:
        print "Which classes are we performing poorly on?"
        labels = list(set(flatten(labels_validation)) | set(flatten(predictions)))
        prfs = sklearn.metrics.precision_recall_fscore_support(
            labels_validation,
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
    prepare_classifier(args.debug)
