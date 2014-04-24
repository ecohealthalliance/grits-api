import argparse
import pickle
import numpy as np
from extract_features import extract_features


clf = pickle.load(open("classifier.p", "rb"))
found_keywords = pickle.load(open("found_keywords.p", "rb"))

def diagnose(content):
    feature_dict = extract_features([{
        'cleanContent' : content
    }]).next()
    print "Keywords found:"
    print feature_dict
    if len(feature_dict) == 0: return
    feature_vector = np.zeros(len(found_keywords))
    for keyword, count in feature_dict.items():
        try:
            feature_vector[found_keywords.index(keyword)] = count
        except ValueError as e:
            print e
    prediction = clf.predict(feature_vector)[0]
    print prediction
    return {'features': feature_dict, 'disease': prediction}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('content', metavar='content', type=str, help='Text to diagnose')
    args = parser.parse_args()
    content = args.content

    diagnose(content)
