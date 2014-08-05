# load the training/validation resources and ontology data from AWS
from boto.s3.connection import S3Connection, Location
import datetime
import os
import pickle
import config
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
            local_copy_time = datetime.datetime.fromtimestamp(os.path.getctime(filename))
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

training_set = get_pickle('training.p')
validation_set = get_pickle('validation.p')
ontologies = get_pickle('ontologies.p')

# Process the ontologies
def get_keyword_sets(*names):
    blocklist = set(['can', 'don', 'dish', 'ad', 'mass', 'yellow'])
    keyword_sets = {}
    for name in names:
        obj = ontologies[name]
        kws = None
        if isinstance(obj, dict):
            kws = obj.keys()
        else:
            kws = obj
        keyword_sets[name] = set([
            unicode(kw.lower().strip())
            for kw in kws
            if kw.upper() != kw
        ]) - blocklist
    return keyword_sets

keyword_sets = get_keyword_sets(
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
    'biocaster/symptoms',
    'wordnet/season',
    'wordnet/climate',
    'wordnet/pathogens',
    'wordnet/hosts',
    'biocaster/pathogens',
    'symp/symptoms',
    'doid/has_symptom',
    'doid/transmitted_by',
    'doid/located_in',
    'wordnet/mod/severe',
    'wordnet/mod/painful',
    'wordnet/mod/large',
    'doid/diseases',
    'eha/disease'
)
keywords_to_extract = set().union(*keyword_sets.values())

# Keyword Extraction
import diagnosis
from diagnosis.KeywordExtractor import *
import numpy as np
import re
import sklearn
from sklearn.pipeline import Pipeline

keyword_links = {k : set() for k in keywords_to_extract}
for category in keyword_sets.keys():
    keyword_set = ontologies[category]
    if isinstance(keyword_set, dict):
        for kwd, cur_links in keyword_set.items():
            kwd = unicode(kwd.lower().strip())
            if kwd not in keywords_to_extract: continue
            cur_links = set([unicode(l.lower().strip()) for l in cur_links])
            keyword_links[kwd] |= cur_links

extract_features = Pipeline([
    ('kwext', KeywordExtractor(keywords_to_extract)),
    ('link', LinkedKeywordAdder(keyword_links)),
    ('limit', LimitCounts(1)),
])

disease_to_parent = {
    'HFM-CoxsackieA' : 'Hand, Foot and Mouth Disease',
    'HFM-Enterovirus71' : 'Hand, Foot and Mouth Disease',
    'Algae' : 'Environmental',
    'Avian Influenza' : 'Influenza',
    'Avian Influenza H7N9' : 'Avian Influenza',
    'Canine Influenza' : 'Influenza',
    'Equine Influenza' : 'Influenza',
    'Cold' : 'Influenza',
    # How do we distinguish these without using the disease name?
    'Swine Flu H1N1' : 'Influenza',
    'Swine Flu H3N2' : 'Influenza',
    'Valley Fever' : 'Fever',
    'African Swine Fever' : 'Fever',
    'Classical Swine Fever' : 'Fever',
    'Crimean-Congo Hemorrhagic Fever' : 'Fever',
    'Yellow Fever' : 'Fever',
    'Rift Valley Fever' : 'Fever',
    'Rocky Mountain Spotted Fever' : 'Fever',
    'Dengue' : 'Fever',
    'Classical Swine Fever' : 'Fever',
    'Hepatitis A' : 'Hepatitis',
    'Hepatitis B' : 'Hepatitis',
    'Hepatitis C' : 'Hepatitis',
    'Hepatitis E' : 'Hepatitis',
    'Meningitis - Strep/Pneumoccocal' : 'Meningitis',
    'Meningitis - Neisseria' : 'Meningitis',
    'Fungal Meningitis' : 'Meningitis',
    'Viral Meningitis' : 'Meningitis',
    'Japanese Encephalitis' : 'Encephalitis',
    'La Crosse Encephalitis' : 'Encephalitis',
    # This is problematic for a number of reasons.
    # Should viruses that cause diseases be labels?
    # And Gastroenteritis is in our symptom keyword set.
    # Dividing keywords between symptoms, 
    # pathogens and diseases seems to be a difficult problem in general.
    'Rotavirus' : 'Gastroenteritis',
    'Sapovirus' : 'Gastroenteritis', 
    'Norovirus' : 'Gastroenteritis',
    'Lyme Disease' : 'Tick-borne disease',
}

label_overrides = {
    '532c9a73f99fe75cf538331c' : 'Fungal Meningitis',
    # Foot and Mouth disease rarely affects humans.
    # This sounds like it should be HFM
    '53303a44f99fe75cf5390a56' : 'Hand, Foot and Mouth Disease',
    '532c9b63f99fe75cf5383521' : 'Gastroenteritis',
    '532cc391f99fe75cf5389989' : 'Tuberculosis'
}

labels_to_omit = [
    'Not Yet Classified',
    'Undiagnosed',
    #Pathogen labels:
    'Food-related toxin',
    'Free Living Amoeba',
    'Pests',
    'Bite',
    'E. coli',
    'Algae',
    'Amoeba',
    #Labels I'm not sure what to make of:
    'Vaccine Complication',
    'Environmental',
    'Conflict',
    'Animal Die-off',
    'Poisoning',
    'Cold',
]

def get_features_and_classifications(
    feature_dicts,
    my_dict_vectorizer,
    resources):
    # features = [
    #     [article1_kewword1_count, article1_keyword2_...],
    #     [article2_kewword1_count, article2_keyword2_...],
    #     ...
    # ]
    # classifications = [
    #     article1_disease, ...
    # ]
    features = []
    classifications = []
    resources_used = []
    for feature_vector, r in zip(my_dict_vectorizer.transform(feature_dicts), resources):
        if feature_vector.sum() == 0:
            #Skip all zero features
            continue
        if r['meta']['disease'] in labels_to_omit:
            continue
        if r['_id'] in label_overrides:
            diseases = [label_overrides[r['_id']]]
        else:
            diseases = [r['meta']['disease']]
        while diseases[-1] in disease_to_parent:
            diseases.append(disease_to_parent[diseases[-1]])
        features.append(feature_vector)
        classifications.append(diseases)
        resources_used.append(r)
    return np.array(features), np.array(classifications), resources_used

from sklearn.feature_extraction import DictVectorizer
train_feature_dicts = extract_features.transform([
    r['cleanContent'] for r in training_set
])
validation_feature_dicts = extract_features.transform([
    r['cleanContent'] for r in validation_set
])
#If we get sparse rows working with the classifier this might yeild some
#performance improvments.
my_dict_vectorizer = DictVectorizer(sparse=False).fit(train_feature_dicts)
print 'found keywords:', len(my_dict_vectorizer.vocabulary_)
print "Many keywords in the validation set do not appear in the training set:"
print  set(DictVectorizer(sparse=False).fit(validation_feature_dicts).vocabulary_) - set(my_dict_vectorizer.vocabulary_)

#Training

feature_mat_train, labels_train, resources_train = get_features_and_classifications(train_feature_dicts, my_dict_vectorizer, training_set)
feature_mat_validation, labels_validation, resources_validation = get_features_and_classifications(validation_feature_dicts, my_dict_vectorizer, validation_set)

print "artlces we could extract keywords from:"
print len(resources_validation), '/', len(validation_set)

#Check for duplicate features:

unique_features = {}
for feature_a, resource_a in zip(feature_mat_train, resources_train):
    for feature_b, resource_b in unique_features.items():
        if not all(feature_a == feature_b):
            print "Duplicate found:"
            print resource_url(resource_a['_id'])
            print resource_url(resource_b['_id'])
            print feature_a
            break
        unique_features.append(feature_a)
        
print "Labels in the validation set that we are sure to miss because we have no training data for them:"
def flatten(li):
    for subli in li:
        for it in subli:
            yield it
not_in_train = [
    y for y in flatten(labels_validation)
    if (y not in flatten(labels_train))
]
print len(not_in_train),'/',len(labels_validation)
print not_in_train

from sklearn.multiclass import OneVsRestClassifier
from sklearn.linear_model import LogisticRegression

my_classifier = OneVsRestClassifier(LogisticRegression(
    # When fit intercept is False the classifier predicts nothing when there are no features.
    # On one hand, predictions based off of nothing could seem puzzling to users.
    # One the other hand, we can guess the article is most likely to be dengue or another common
    # disease and still occassionally be right, and having a intercept offset could allow us
    # to create a model that is a tighter fit.
    # fit_intercept=False
    # l1 penalty will produce sparser coefficients.
    # it seems to perform worse, but the classifications will be easier to inspect,
    # and we might be able to avoid some weak classifications based on weak correlations that turn out to be false.
    # penalty='l1',
    # Using class weighting we might be able to avoid overpredicting the more common labels.
    # However, auto weighting has only hurt our f-scores so far.
    # class_weight='auto',
), n_jobs=-1)

my_classifier.fit(feature_mat_train, labels_train)

# Pickle everything that will be needed for classification
with open('classifier.p', 'wb') as f:
    pickle.dump(my_classifier, f)
with open('dict_vectorizer.p', 'wb') as f:
    pickle.dump(my_dict_vectorizer, f)
with open('keyword_links.p', 'wb') as f:
    pickle.dump(keyword_links, f)
with open('keyword_sets.p', 'wb') as f:
    pickle.dump(keyword_sets, f)

# Classification

from diagnosis.Diagnoser import Diagnoser
with open('classifier.p') as f:
    my_classifier = pickle.load(f)
with open('dict_vectorizer.p') as f:
    my_dict_vectorizer = pickle.load(f)
with open('keyword_links.p') as f:
    keyword_links = pickle.load(f)
with open('keyword_sets.p') as f:
    keyword_sets = pickle.load(f)
my_diagnoser = Diagnoser(my_classifier,
                         my_dict_vectorizer,
                         keyword_links=keyword_links,
                         keyword_categories=keyword_sets,
                         cutoff_ratio=.7)

print "macro average:"
training_predictions = [
    tuple([my_diagnoser.classifier.classes_[i] for i, p in my_diagnoser.best_guess(X)])
    for X in feature_mat_train
]
print "Training set:\nprecision: %s recall: %s f-score: %s" %\
    sklearn.metrics.precision_recall_fscore_support(labels_train, training_predictions, average='macro')[0:3]

predictions = training_predictions = [
    tuple([my_diagnoser.classifier.classes_[i] for i, p in my_diagnoser.best_guess(X)])
    for X in feature_mat_validation
]
prfs = sklearn.metrics.precision_recall_fscore_support(labels_validation, predictions)
# I've noticed that the macro f-score is not the harmonic mean of the percision
# and recall. Perhaps this could be a result of the macro f-score being computed 
# as an average of f-scores.
# Furthermore, the macro f-scrore can be smaller than the precision and
# recall which seems like it shouldn't be possible.
print "Validation set:\nprecision: %s recall: %s f-score: %s" %\
    sklearn.metrics.precision_recall_fscore_support(
        labels_validation,
        predictions,
        average='macro')[0:3]
print "micro average:"
print "precision: %s recall: %s f-score: %s" %\
    sklearn.metrics.precision_recall_fscore_support(labels_validation,
    predictions,
    average='micro')[0:3]

print "Which classes are we performing poorly on?"

labels = list(set(flatten(labels_validation)) | set(flatten(predictions)))
prfs = sklearn.metrics.precision_recall_fscore_support(labels_validation, predictions, labels=labels)
for cl,p,r,f,s in sorted(zip(labels, *prfs), key=lambda k:k[3]):
    print cl
    print "precision:",p,"recall",r,"F-score:",f,"support:",s
