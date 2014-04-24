from extract_features import extract_features

def get_keywords():
    import nltk
    synset = nltk.wordnet.wordnet.synsets("pathogens")[0].hypernyms() + nltk.wordnet.wordnet.synsets("virus")
    def traverse_hyponyms(synset, depth=3):
        for syn in synset:
            yield syn.name.split('.')[0].replace('_', ' ')
            if depth > 0:
                for hypo in traverse_hyponyms(syn.hyponyms(), depth-1):
                    yield hypo

    pathogen_names = set(traverse_hyponyms(synset))

    import bson
    with open("tags.bson", 'rb') as f:
        result = bson.decode_all(f.read())
        pm_keywords = {}

        for tag in result:
            try:
                #I'm not sure if we should throw out the case information just yet...
                tag_name = unicode(tag.get('name').strip().lower())

                #Remove some of the compound tags
                if "(" in tag_name or "," in tag_name:
                    continue
                if tag_name.startswith("the "):
                    tag_name = tag_name[4:]
                if tag_name.endswith(" and"):
                    tag_name = tag_name[:-4]
                #and remove long tags that we are unlikely to find
                if len(tag_name) > 30:
                    continue
                if 'category' in tag:
                    cat = tag['category']
                    if cat in pm_keywords:
                        pm_keywords[cat].add(tag_name)
                    else:
                        pm_keywords[cat] = set([tag_name])
            except:
                print tag

    tag_blacklist = set(['can', 'don', 'dish', 'ad', 'mass', 'yellow'])

    diseases = pm_keywords['disease']
    symptoms = pm_keywords['symptom']

    #These are from the HM labels.
    #Many that we were missing affect animals.
    extra_diseases = set([
     'bacterial meningitis',
     'blue ear',
     'bovine tb',
     'chagas',
     'chicken pox',
     'cjd',
     'crimean-congo hemorrhagic fever',
     'echinococcosis',
     'guinea worm',
     'hand , foot and mouth disease',
     'hantavirus',
    #hand foot and mouth cause, maybe should be treated as a synonym?
     'hfm-coxsackiea',
     'hiv/aids',
     "legionnaires'",
     'leishmaniasis',
     'nipah/hendra virus',
     'norovirus',
     'schmallenberg',
     'strangles',
     'swine flu',
     'h1n1',
     'white-nose syndrome', 'white nose syndrome'
    ])
    diseases |= extra_diseases

    symptoms -= tag_blacklist
    diseases = diseases - tag_blacklist

    synset = nltk.wordnet.wordnet.synsets("insect") +\
        nltk.wordnet.wordnet.synsets("animal") +\
        nltk.wordnet.wordnet.synsets("mammal") +\
        [nltk.wordnet.wordnet.synsets('plant')[1]]
    def traverse_hyponyms(synset, depth=3):
        for syn in synset:
            yield syn.name.split('.')[0].replace('_', ' ')
            if depth > 0:
                for hypo in traverse_hyponyms(syn.hyponyms(), depth-1):
                     yield hypo

    #Definately an incomplete list:
    non_host_names = set(['sponge', 'pest', 'mate',
                          'big game', 'prey',
                          'young', 'worker', 'head',
                          'carnivore',
                          'giant',
                          'medusa'])
    probably_not_host_names = set([
        'soldier',
        'pooch', 'kitten',
        'game',
        'mastodon',
        'adult', 'male', 'female', 'baby',
        'lapdog', 'young bird',
        'young fish'
    ])
    host_names = set(traverse_hyponyms(synset)) - non_host_names - probably_not_host_names

    import json
    with open("keywords.json", 'wb') as f:
        json.dump({
            'hosts' : list(host_names),
            'pathogens' : list(pathogen_names),
            'symptoms' : list(symptoms),
            'diseases' : list(diseases)
        }, f)


def train_classifier():
    from corpora import iterate_resources
    resources = list(iterate_resources.iterate_resources("corpora/healthmap/train"))
    print "train set size:", len(resources)

    def fetch_translations(path):
        import os, json
        translations = []
        for root, dirs, files in os.walk(path):
            for file_name in files:
                if not file_name.endswith('.json'): continue
                file_path = os.path.join(root, file_name)
                with open(file_path) as f:
                    translations.extend(json.load(f))
        return translations
    def translations_to_dict(translation_roa):
        translations = {}
        for translation in translation_roa:
            translations[translation['id']] = translation['translation']
        return translations

    translations = translations_to_dict(fetch_translations('corpora/translations'))

    import random
    import ctypes
    test_data = []
    def pseudo_random_subset(resources, portion):
        """
        Uses the resource id to deterministically choose whether
        to include it in a pseudorandom subset.
        Because the ids are also used to determine the category
        to avoid bias we take their random hash modulo .1
        as only the first decimal is used to determine the data set.
        """
        for resource in resources:
            #Oh if only I had used hashlib from the beginning!
            #The hashes that the RNG seed function creates are platform dependent
            #so 64 bit systems return different random values.
            #However, we can get 32 bit system hashes on 64 bit systems by bitmasking the hash.
            #Since the python bitwise operators return uints we also need to covert the to signed values via ctypes.
            resource_id_hash = ctypes.c_int32(hash(resource.get('_id')) & 0xffffffff).value
            random_value = random.Random(resource_id_hash).random()
            test_data.append({
                'rv' : random_value,
                '_id' : resource.get('_id'),
                'hash' : resource_id_hash
            })
            if 10 * (random_value % .1) < portion:
                yield resource
    original_resource_subset = list(pseudo_random_subset(resources, .04))
    print "train set size: ", len(original_resource_subset)

    import goose
    from bs4 import BeautifulSoup
    def resource_url(id, set_name="train"):
        return "https://github.com/ecohealthalliance/corpora/blob/fetch_4-18-2014/healthmap/" + set_name + "/" + id + ".md"
    def preprocess_resources(resources, set_name="train"):
        for resource in resources:
            if resource['_id'] in translations:
                resource['cleanContent'] = translations[resource['_id']]
                yield resource
                continue
            content = resource.get('content')
            if resource.get('sourceMeta').get('unscrapable'):
                #print "Skipping resource because it could not be scrapped:", resource_url(resource.get("_id"), set_name)
                continue
            if not content.startswith('<html>'):
                content = '<html><body>' + content + '</body></html>'
            try:
                cleaned_content = goose.Goose({
                    'parser_class':'soup',
                    'enable_image_fetching' : False,
                }).extract(raw_html=content).cleaned_text
                if len(cleaned_content) < 1:
                    #Goose doesn't do well with foreign language content.
                    #If we can't find content with goose try extracting
                    #all the text with Beautiful soup.
                    #Beautiful soup doesn't attempt to extract the article,
                    #it just finds all the text in the html, which seems to be
                    #good enough since we've already used readability on the articles.
                    cleaned_content = BeautifulSoup(content).text
                if len(cleaned_content) < 50:
                    #Most of the articles with content this short don't
                    #have any content we would want to extract.
                    print "Skipping resource " + resource['_id'] + " due to lack of content."
                    print "content extracted:", cleaned_content
                    continue
                resource['cleanContent'] = cleaned_content
                yield resource
            except:
                print "Could not clean:", resource['_id']
    resource_subset = list(preprocess_resources(original_resource_subset))
    print "Resources processed:", len(resource_subset),'/',len(original_resource_subset)

    import numpy as np
    def get_features_and_classifications(resources, keywords):
        # features = [
        #     [article1_kewword1_count, article1_keyword2_...],
        #     [article2_kewword1_count, article2_keyword2_...],
        #     ...
        # ]
        # classifications = [
        #     article1_disease, ...
        # ]
        feature_dicts = list(extract_features(resources))
        features = []
        classifications = []
        resources_used = []
        for fd, r in zip(feature_dicts, resources):
            feature_vector = np.zeros(len(keywords))
            for keyword, count in fd.items():
                try:
                    feature_vector[keywords.index(keyword)] = count
                except ValueError as e:
                    print e
            if all(feature_vector == np.zeros(len(keywords))):
                #Skip all zero features
                continue
            features.append(feature_vector)
            classifications.append(r['meta']['disease'])
            resources_used.append(r)
        return np.array(features), np.array(classifications), resources_used

    feature_dicts = list(extract_features(resource_subset))
    found_keywords = set()
    for fd in feature_dicts:
        found_keywords |= set(fd.keys())
    found_keywords = list(found_keywords)

    X_train, y_train, resources_train = get_features_and_classifications(resource_subset, found_keywords)

    from sklearn.linear_model import LogisticRegression

    clf = LogisticRegression()
    clf.fit(X_train, y_train)

    import pickle
    pickle.dump(found_keywords, open("found_keywords.p", "wb"))
    pickle.dump(clf, open( "classifier.p", "wb" ))

if __name__ == '__main__':
    #get_keywords()
    train_classifier()
