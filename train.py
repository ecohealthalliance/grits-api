
# coding: utf-8

# ### Loading the resources from the corpora repository on the local file system.
# This could take a few minutes...

# In[4]:

import datetime
from corpora import iterate_resources
start = datetime.datetime.now()
resources = list(iterate_resources.iterate_resources("corpora/healthmap/train"))
validation_resources = list(iterate_resources.iterate_resources("corpora/healthmap/devtest"))
print "full train set size:", len(resources)
print "full validation set size:", len(validation_resources)
original_resource_subset = list(iterate_resources.pseudo_random_subset(resources, 1.0))
print "train subset size: ", len(original_resource_subset)
original_validation_subset = list(iterate_resources.pseudo_random_subset(validation_resources, .04))
print "validation subset size: ", len(original_validation_subset)
print "time:", datetime.datetime.now() - start


# In[5]:

import corpora.process_resources
from corpora.process_resources import resource_url, process_resources, attach_translations, filter_exceptions, resource_url
start = datetime.datetime.now()
attach_translations(original_resource_subset + original_validation_subset)
resource_subset, train_exceptions = filter_exceptions(process_resources(original_resource_subset))
validation_subset, validation_exceptions = filter_exceptions(process_resources(original_validation_subset))
print "Training resources processed:", len(resource_subset),'/',len(original_resource_subset)
print "Validation resources processed:", len(validation_subset),'/',len(original_validation_subset)
print "time:", datetime.datetime.now() - start


# In[6]:

# Training resources processed: 11211 / 21300
# Validation resources processed: 153 / 297
# time: 0:01:06.039331


# ## Load keywords to use for tagging
# 
# The keywords are extracted in the [Ontologies notebook](Ontologies.ipynb)

# In[35]:

import pickle
with open("ontologies.p") as f:
    ontologies = pickle.load(f)
    print ontologies.keys()


# In[151]:

def get_keyword_sets(*names):
    keyword_sets = {}
    for name in names:
        obj = ontologies[name]
        kws = None
        if isinstance(obj, dict):
            kws = obj.keys()
        else:
            kws = obj
        keyword_sets[name] = set([unicode(kw.lower().strip()) for kw in kws
                                  if kw.upper() != kw])
    return keyword_sets

keyword_sets = get_keyword_sets(
    'pm_symptom',
    'pm_mode of transmission',
    'pm_environmental factors',
    'biocaster_symptoms',
    'wordnet_season',
    'wordnet_climate',
    'wordnet_pathogens',
    'wordnet_hosts',
    'biocaster_pathogens',
    'symp_symptoms',
    'doid_has_symptom',
    'doid_transmitted_by',
    'doid_located_in',
    'wordnet_mod_severe',
    'wordnet_mod_painful',
    'wordnet_mod_large'
)
keywords_to_extract = set().union(*keyword_sets.values())

# ## Feature Extraction
# 
# See the feature extraction notebook for more details on why this approach was chosen.

# In[153]:

import diagnosis
from diagnosis.KeywordExtractor import *
import numpy as np
import re
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
    # Dividing keywords between symptoms, pathogens and diseases seems to be a difficult problem in general.
    'Rotavirus' : 'Gastroenteritis',
    'Norovirus' : 'Gastroenteritis',
    'Lyme Disease' : 'Tick-borne disease',
}
def get_features_and_classifications(feature_dicts, my_dict_vectorizer, resources):
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
        if r['meta']['disease'] == 'Not Yet Classified' or r['meta']['disease'] == 'Undiagnosed':
            continue
        diseases = [r['meta']['disease']]
        while diseases[-1] in disease_to_parent:
            diseases.append(disease_to_parent[diseases[-1]])
        features.append(feature_vector)
        classifications.append(diseases)
        resources_used.append(r)
    return np.array(features), np.array(classifications), resources_used


# In[154]:

from sklearn.feature_extraction import DictVectorizer
train_feature_dicts = extract_features.transform([r['cleanContent'] for r in resource_subset])
validation_feature_dicts = extract_features.transform([r['cleanContent'] for r in validation_subset])
#If we get sparse rows working with the classifier this might yeild some performance improvments.
my_dict_vectorizer = DictVectorizer(sparse=False).fit(train_feature_dicts)
print 'found keywords:', len(my_dict_vectorizer.vocabulary_)
print "Many keywords in the validation set do not appear in the training set:"
print  set(DictVectorizer(sparse=False).fit(validation_feature_dicts).vocabulary_) - set(my_dict_vectorizer.vocabulary_)


# In[155]:

cv = CountVectorizer(vocabulary=keywords_to_extract, ngram_range=(1, 4))
v = cv.transform([r['cleanContent'] for r in validation_subset[1:4]])
for r in range(v.shape[0]):
    for c in v[r].nonzero()[1]:
        print cv.get_feature_names()[c], v[r,c]
#set(flatten(list(cv.inverse_transform(v))))


# ##Training

# In[156]:

X_train, y_train, resources_train = get_features_and_classifications(train_feature_dicts, my_dict_vectorizer, resource_subset)
X_validation, y_validation, resources_validation = get_features_and_classifications(validation_feature_dicts, my_dict_vectorizer, validation_subset)

# In[158]:

#Check for duplicate features:
unique_features = {}
for feature_a, resource_a in zip(X_train, resources_train):
    for feature_b, resource_b in unique_features.items():
        if not all(feature_a == feature_b):
            print "Duplicate found:"
            print resource_url(resource_a['_id'])
            print resource_url(resource_b['_id'])
            print feature_a
            break
        unique_features.append(feature_a)

# #### Labels in the validation set that we are sure to miss because we have no training data for them:

# In[159]:

def flatten(li):
    for subli in li:
        for it in subli:
            yield it
not_in_train = [y for y in flatten(y_validation) if (y not in flatten(y_train))]
print len(not_in_train),'/',len(y_validation)
print not_in_train


# #### Classified artlces we could extract keywords from:

# In[160]:

print len(resources_validation), '/', len(validation_subset)


# # Classification

# In[165]:

from matplotlib.colors import ListedColormap
import matplotlib.pyplot as plt
import sklearn
from sklearn.cross_validation import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, AdaBoostClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.lda import LDA
from sklearn.qda import QDA
from sklearn.multiclass import OneVsRestClassifier
from sklearn.linear_model import LogisticRegression

best_clf = OneVsRestClassifier(LogisticRegression(
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
    # class_weight='auto',
), n_jobs=-1)

best_clf.fit(X_train, y_train)


# In[166]:

get_ipython().magic(u'load_ext autoreload')
get_ipython().magic(u'autoreload 2')
import diagnosis.Diagnoser
from diagnosis.Diagnoser import Diagnoser
import funcy
my_diagnoser = Diagnoser(best_clf, my_dict_vectorizer, keyword_links=keyword_links, keyword_categories=keyword_sets, cutoff_ratio=.65)

print "macro average:"
training_predictions = [
    tuple([my_diagnoser.classifier.classes_[i] for i, p in my_diagnoser.best_guess(X)])
    for X in X_train
]
print "Training set:\nprecision: %s recall: %s f-score: %s" %    sklearn.metrics.precision_recall_fscore_support(y_train, training_predictions, average='macro')[0:3]
    
diagnoses = [my_diagnoser.diagnose(r['cleanContent']) for r in resources_validation] 
predictions = [funcy.pluck('name', d['diseases']) for d in diagnoses]
prfs = sklearn.metrics.precision_recall_fscore_support(y_validation, predictions)
print "Validation set:\nprecision: %s recall: %s f-score: %s" %    sklearn.metrics.precision_recall_fscore_support(y_validation, predictions, average='macro')[0:3]
print "micro average:"
print "precision: %s recall: %s f-score: %s" %    sklearn.metrics.precision_recall_fscore_support(y_validation, predictions, average='micro')[0:3]


# In[167]:

# Validation set:
# precision: 0.521697070205 recall: 0.539226660814 f-score: 0.519249282045
# micro average:
# precision: 0.629441624365 recall: 0.71676300578 f-score: 0.67027027027


# ### Which classes are we performing poorly on?

# In[168]:

labels = list(set(flatten(y_validation)) | set(flatten(predictions)))
prfs = sklearn.metrics.precision_recall_fscore_support(y_validation, predictions, labels=labels)
for cl,p,r,f,s in sorted(zip(labels, *prfs), key=lambda k:k[3]):
    print cl
    print "precision:",p,"recall",r,"F-score:",f,"support:",s

# In[171]:

# I think we should pickle the diagnoser becaused it might contain
# additional parameters e.g. cutoff_ratio
# that affect the classification accuracy,
# and it allows us to avoid creating separate pickles for the keywords.
import pickle
with open('diagnoser.p', 'wb') as f:
    pickle.dump(my_diagnoser, f)
