#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""train_and_validate_multi.py: Experiments in multi-level GRITS classification"""

__author__ = "rhorton@ecohealth.io"

from corpora import iterate_resources
import corpora.process_resources
from corpora.process_resources import resource_url, process_resources, attach_translations, filter_exceptions, resource_url
import diagnosis.Diagnoser
from diagnosis.Diagnoser import Diagnoser
from utils import timed

from collections import defaultdict
from time import time
import pickle as pickle
import diagnosis
from diagnosis.KeywordExtractor import *
import numpy as np
import re
import funcy
import sklearn
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction import DictVectorizer
from sklearn.multiclass import OneVsRestClassifier
from sklearn.linear_model import LogisticRegression

class TrainAndValidate():

    cutoff_ratio = 0.7

    def main(self):

        # self.dump_corpora_pickles()

        training, validation = self.load_corpora_pickles()

        training_subset = list(iterate_resources.pseudo_random_subset(training, 1.0))
        validation_subset = list(iterate_resources.pseudo_random_subset(validation, .1))
        print "training subset: ", len(training_subset),  '/', len(training)
        print "validation subset: ", len(validation_subset),  '/', len(validation)

        print "Attaching translations..."
        attach_translations(training_subset + validation_subset)
        print "Translations attached."

        print "Filtering training and validation data..."
        # self.dump_filtered_data(training_subset, validation_subset)
        training_filtered, validation_filtered = self.load_filtered_data()
        print "Training data retained:", len(training_filtered), '/', len(training_subset)
        print "Validation data retained:", len(validation_filtered), '/', len(validation_subset)

        print "Loading ontologies"
        ontologies = self.load_ontologies()
        print "Ontologies loaded, keys:"
        print ontologies.keys()        

        keyword_keys = [
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
            'wordnet_mod_large']

        keyword_sets = self.get_keyword_sets(keyword_keys, ontologies)
        keywords_to_extract = set().union(*keyword_sets.values())

        print "Getting keyword_links..."
        keyword_links = self.get_keyword_links(ontologies, keyword_sets, keywords_to_extract)

        print "Loading feature_dicts..."
        # self.dump_feature_dicts(training_filtered, validation_filtered,
        #                         keywords_to_extract, keyword_links)
        training_feature_dicts, validation_feature_dicts = self.load_feature_dicts()

        # If we get sparse rows working with the classifier this might yeild
        # some performance improvments.
        dict_vectorizer = DictVectorizer(sparse=False).fit(training_feature_dicts)
        print 'found keywords:', len(dict_vectorizer.vocabulary_)
        print "Keywords in validation not in training:"
        print (set(DictVectorizer(sparse=False).fit(validation_feature_dicts).vocabulary_) -
              set(dict_vectorizer.vocabulary_))

        # Transform keywords
        cv = CountVectorizer(vocabulary=keywords_to_extract, ngram_range=(1, 4))
        v = cv.transform([r['cleanContent'] for r in validation_filtered[1:4]])
        for r in range(v.shape[0]):
            for c in v[r].nonzero()[1]:
                print cv.get_feature_names()[c], v[r,c]

        X_training, y_training, resources_training = self.get_features_and_classifications(
            training_feature_dicts, dict_vectorizer, training_filtered)
        
        X_validation, y_validation, resources_validation = self.get_features_and_classifications(
            validation_feature_dicts, dict_vectorizer, validation_filtered)

        self.write_label_distributions(y_training)

        labels_in_training = set([ label for labels in y_training for label in labels ])
        labels_in_validation = set([ label for labels in y_validation for label in labels ])

        only_in_training = labels_in_training.symmetric_difference(labels_in_validation).intersection(labels_in_training)

        only_in_validation = labels_in_validation.symmetric_difference(labels_in_training).intersection(labels_in_validation)

        print "only_in_training:", only_in_training
        print "only_in_validation:", only_in_validation

        label_counts = defaultdict(int)
        num_label_counts = defaultdict(int)
        for labels in y_training:
            num_label_counts[len(labels)] += 1
            for label in labels:
                label_counts[label] += 1
        for labels in y_validation:
            num_label_counts[len(labels)] += 1
            for label in labels:
                label_counts[label] += 1
        print "num_label_counts:", num_label_counts
        print "label_counts:", label_counts

        print "Getting and fitting classifier..."
        classifier = self.get_fit_and_dump_one_v_rest_classifier(X_training, y_training)
        classifier = self.load_classifier()
        print "Classifier loaded."

        # training_predictions = self.get_classifier_predictions(classifier, X_training)
        validation_predictions = self.get_classifier_predictions(classifier, X_validation)
        print "Got validation_predictions"

        prediction_counts = defaultdict(int)
        for labels in validation_predictions: prediction_counts[len(labels)] += 1
        print "prediction_counts:", prediction_counts

        # print "Training set:\nprecision: %s recall: %s f-score: %s" % sklearn.metrics.precision_recall_fscore_support(y_train, training_predictions, average='macro')[0:3]
        print "Validation set:\nprecision: %s recall: %s f-score: %s" % \
            sklearn.metrics.precision_recall_fscore_support(y_validation, validation_predictions, average='macro')[0:3]

        self.get_metrics_with_multilevel_awareness(validation_predictions, y_validation)

    @timed
    def write_label_distributions(self, data, filename="label_data.csv"):

        all_labels = set()
        label_counts = defaultdict(int)
        num_label_counts = defaultdict(int)
        label_num_label_counts = defaultdict(lambda: defaultdict(int))

        for labels in data:
            num_label_counts[len(labels)] += 1
            for label in labels:
                all_labels.add(label)
                label_counts[label] += 1
                label_num_label_counts[label][len(labels)] += 1
        print "num_label_counts:", num_label_counts
        print "label_counts:", label_counts

        fields = ['label', 'count', 'percentage', '1-label', '2-label', '3-label', 'parent', 'child', 'unlinked']
        fp = open(filename, 'wb')

        fp.write(','.join(fields) + '\n')
        
        for label in all_labels:
            is_parent = '0'
            is_child = '0'
            is_unlinked = '0'
            if label in self.disease_to_parent:
                is_child = '1'
            if label in self.parent_to_diseases:
                is_parent = '1'
            if (is_parent == '0') and (is_child == '0'):
                is_unlinked = '1'

            values = ['"' + label + '"',
                      str(label_counts[label]),
                      str((label_counts[label] / float(len(data))) * 100),
                      str(label_num_label_counts[label][1]),
                      str(label_num_label_counts[label][2]),
                      str(label_num_label_counts[label][3]),
                      is_parent,
                      is_child,
                      is_unlinked]
            fp.write(','.join(values) + '\n')

        fp.close()


    @timed
    def get_classifier_predictions(self, classifier, data):
        return [ tuple([classifier.classes_[i] for i, p in self.best_guess(classifier, X)])
                 for X in data ]

    def best_guess(self, classifier, X):
        probs = classifier.predict_proba(X)[0]
        p_max = max(probs)
        return [(i,p) for i,p in enumerate(probs) if p >= p_max * self.cutoff_ratio]

    @timed
    def get_metrics_with_multilevel_awareness(self, validation_predictions, y_validation):

        # correct prediction, disease is parent
        right_parent = 0
        # correct prediction, disease is child
        right_child = 0
        # prediction was the parent of the label
        prediction_was_label_parent = 0
        # prediction was one of the label children
        prediction_was_label_child = 0
        # incorrect prediction, predicted is parent, true label is parent
        wrong_parent_predicted_parent_true = 0
        # incorrect prediction, predicted is parent, true label is child
        wrong_parent_predicted_child_true = 0
        # incorrect prediction, predicted is child, true label is child
        wrong_child_predicted_child_true = 0
        # incorrect prediction, predicted is child, true label is parent
        wrong_child_predicted_parent_true = 0

        for predictions, labels in zip(validation_predictions, y_validation):

            if (len(predictions) == 1 and len(labels) == 1):

                prediction = predictions[0]
                label = labels[0]

                prediction_parent = None
                label_parent = None
                prediction_children = []
                label_children = []

                # print "prediction:", prediction
                # print "label:", label

                if prediction in self.parent_to_diseases:
                    prediction_is_parent = True
                    prediction_children = self.parent_to_diseases[prediction]
                elif prediction in self.disease_to_parent:
                    prediction_is_child = True
                    prediction_parent = self.disease_to_parent[prediction]
                else:
                    pass
                    # print "prediction:", prediction, "is neither parent nor child"

                if label in self.parent_to_diseases:
                    label_is_parent = True
                    label_children = self.parent_to_diseases[label]
                elif label in self.disease_to_parent:
                    label_is_child = True
                    label_parent = self.disease_to_parent[label]
                else:
                    pass
                    # print "label:", label, "is neither parent nor child"

                if prediction == label:
                    if prediction_is_parent:
                        right_parent += 1
                    else:
                        right_child += 1
                elif prediction == label_parent:
                    prediction_was_label_parent += 1
                elif prediction in label_children:
                    prediction_was_label_child += 1
                else:
                    if prediction_is_parent and label_is_parent:
                        wrong_parent_predicted_parent_true
                    elif prediction_is_parent and label_is_child:
                        wrong_parent_predicted_child_true
                    elif prediction_is_child and label_is_parent:
                        wrong_child_predicted_parent_true
                    elif prediction_is_child and label_is_child:
                        wrong_child_predicted_child_true
                    else:
                        pass
                        # print "Prediction or label is neither child nor parent"
                        # print "prediction:", prediction, "label:", label

        print "Total:", len(validation_predictions)
        print "right_parent:", right_parent
        print "right_child:", right_child
        print "prediction_was_label_parent:", prediction_was_label_parent
        print "prediction_was_label_child", prediction_was_label_child
        print "wrong_parent_predicted_parent_true", wrong_parent_predicted_parent_true
        print "wrong_parent_predicted_child_true", wrong_parent_predicted_child_true
        print "wrong_child_predicted_child_true", wrong_child_predicted_child_true
        print "wrong_child_predicted_parent_true", wrong_child_predicted_parent_true

    @staticmethod
    @timed
    def get_diagnoses_and_predictions(diagnoser, data):
        diagnoses = [diagnoser.diagnose(r['cleanContent']) for r in data] 
        predictions = [funcy.pluck('name', d['diseases']) for d in diagnoses]
        return (diagnoses, predictions)


    @staticmethod
    @timed
    def get_fit_and_dump_one_v_rest_classifier(X, y, pickle_filename="one_vs_rest_classifier.pickle"):
        classifier = OneVsRestClassifier(LogisticRegression(), n_jobs=-1)
        classifier.fit(X, y)
        with open(pickle_filename, 'wb') as fp:
            pickle.dump(classifier, fp)
        return classifier

    @staticmethod
    @timed
    def load_classifier(pickle_filename="one_vs_rest_classifier.pickle"):
        with open(pickle_filename, 'rb') as fp:
            classifier = pickle.load(fp)
        return classifier

    @staticmethod
    @timed
    def fit_classifier(classifier, X, y): classifier.fit(X, y)

    @staticmethod
    @timed
    def dump_filtered_data(training_subset, validation_subset,
                           training_filename="training_filtered.pickle",
                           validation_filename="validation_filtered.pickle"):
        
        training_filtered, training_exceptions = filter_exceptions(
            process_resources(training_subset))
        validation_filtered, validation_exceptions = filter_exceptions(
            process_resources(validation_subset))
        
        with open(training_filename, 'wb') as fp:
            pickle.dump(training_filtered, fp)
        with open(validation_filename, 'wb') as fp:
            pickle.dump(validation_filtered, fp)

    @staticmethod
    @timed
    def load_filtered_data(training_filename="training_filtered.pickle",
                           validation_filename="validation_filtered.pickle"):
                
        with open(training_filename, 'rb') as fp:
            training_filtered = pickle.load(fp)
        with open(validation_filename, 'rb') as fp:
            validation_filtered = pickle.load(fp)

        return (training_filtered, validation_filtered)

    @staticmethod
    @timed
    def dump_feature_dicts(training_filtered, validation_filtered,
                           keywords_to_extract, keyword_links,
                           training_filename="training_feature_dicts.pickle",
                           validation_filename="validation_feature_dicts.pickle"):
        
        extract_features = Pipeline([
            ('kwext', KeywordExtractor(keywords_to_extract)),
            ('link', LinkedKeywordAdder(keyword_links)),
            ('limit', LimitCounts(1)),
        ])

        training_feature_dicts = extract_features.transform(
            [r['cleanContent'] for r in training_filtered])
        validation_feature_dicts = extract_features.transform(
            [r['cleanContent'] for r in validation_filtered])
    
        with open(training_filename, 'wb') as fp:
            pickle.dump(training_feature_dicts, fp)
        with open(validation_filename, 'wb') as fp:
            pickle.dump(validation_feature_dicts, fp)

    @staticmethod
    @timed
    def load_feature_dicts(training_filename="training_feature_dicts.pickle",
                           validation_filename="validation_feature_dicts.pickle"):
                
        with open(training_filename, 'rb') as fp:
            training_feature_dicts = pickle.load(fp)
        with open(validation_filename, 'rb') as fp:
            validation_feature_dicts = pickle.load(fp)

        return (training_feature_dicts, validation_feature_dicts)

    
    @staticmethod
    @timed
    def load_ontologies(ontology_filename="ontologies.p"):
        with open(ontology_filename) as ontology_file:
            return pickle.load(ontology_file)

    @staticmethod
    @timed
    def load_corpora_pickles(training_file="training.pickle",
                             validation_file="validation.pickle"):
        """Load test and train data from pickles"""

        with open(training_file, 'rb') as fp:
            training = pickle.load(fp)
        with open(validation_file, 'rb') as fp:
            validation = pickle.load(fp)

        return (training, validation)

    @staticmethod
    @timed
    def get_keyword_sets(names, ontologies):
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

    @staticmethod
    @timed
    def get_keyword_links(ontologies, keyword_sets, keywords_to_extract):
        keyword_links = {k : set() for k in keywords_to_extract}
        for category in keyword_sets.keys():
            keyword_set = ontologies[category]
            if isinstance(keyword_set, dict):
                for kwd, cur_links in keyword_set.items():
                    kwd = unicode(kwd.lower().strip())
                    if kwd not in keywords_to_extract: continue
                    cur_links = set([unicode(l.lower().strip()) for l in cur_links])
                    keyword_links[kwd] |= cur_links
        return keyword_links

    @timed
    def get_features_and_classifications(self, feature_dicts, dict_vectorizer, resources):
        features = []
        classifications = []
        resources_used = []
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
        for feature_vector, r in zip(dict_vectorizer.transform(feature_dicts), resources):
            if feature_vector.sum() == 0:
                #Skip all zero features
                continue
            if r['meta']['disease'] in labels_to_omit:
                continue
            if r['meta']['disease'] == 'Not Yet Classified' or r['meta']['disease'] == 'Undiagnosed':
                continue
            diseases = [r['meta']['disease']]
            while diseases[-1] in self.disease_to_parent:
                diseases.append(self.disease_to_parent[diseases[-1]])
            # TODO Why is this necessary?
            if not None in diseases:
                features.append(feature_vector)
                classifications.append(diseases)
                resources_used.append(r)
        return np.array(features), np.array(classifications), resources_used


    @staticmethod
    @timed
    def find_duplicate_features(X_train, training_filtered):
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

    @staticmethod
    @timed
    def dump_corpora_pickles(train_dir="corpora/healthmap/train",
                             test_dir="corpora/healthmap/devtest"):
        """Dump some pickles of our training and validation data so that we can
        load faster"""

        training = list(iterate_resources.iterate_resources(train_dir))
        validation = list(iterate_resources.iterate_resources(test_dir))

        with open('training.pickle', 'wb') as fp:
            pickle.dump(training, fp)
        with open('validation.pickle', 'wb') as fp:
            pickle.dump(validation, fp)

    disease_to_parent = {
        'HFM-CoxsackieA': 'Hand, Foot and Mouth Disease',
        'HFM-Enterovirus71': 'Hand, Foot and Mouth Disease',
        'Algae': 'Environmental',
        'Avian Influenza': 'Influenza',
        'Avian Influenza H7N9': 'Avian Influenza',
        'Canine Influenza': 'Influenza',
        'Equine Influenza': 'Influenza',
        'Cold': 'Influenza',
        'Swine Flu H1N1': 'Influenza',
        'Swine Flu H3N2': 'Influenza',
        'Valley Fever': 'Fever',
        'African Swine Fever': 'Fever',
        'Classical Swine Fever': 'Fever',
        'Crimean-Congo Hemorrhagic Fever': 'Fever',
        'Yellow Fever': 'Fever',
        'Rift Valley Fever': 'Fever',
        'Rocky Mountain Spotted Fever': 'Fever',
        'Dengue': 'Fever',
        'Classical Swine Fever': 'Fever',
        'Hepatitis A': 'Hepatitis',
        'Hepatitis B': 'Hepatitis',
        'Hepatitis C': 'Hepatitis',
        'Hepatitis E': 'Hepatitis',
        'Meningitis - Strep/Pneumoccocal': 'Meningitis',
        'Meningitis - Neisseria': 'Meningitis',
        'Fungal Meningitis': 'Meningitis',
        'Viral Meningitis': 'Meningitis',
        'Japanese Encephalitis': 'Encephalitis',
        'La Crosse Encephalitis': 'Encephalitis',
        'Rotavirus': 'Gastroenteritis',
        'Norovirus': 'Gastroenteritis',
        'Lyme Disease': 'Tick-borne disease'
    }

    parent_to_diseases = {}

    for disease, parent in disease_to_parent.iteritems():
        if parent in parent_to_diseases:
            parent_to_diseases[parent].append(disease) 
        else:
            parent_to_diseases[parent] = [disease]

if __name__ == '__main__':
    ml = TrainAndValidate()
    ml.main()
