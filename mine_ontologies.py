# coding: utf-8
"""
Mine keywords and their relationships from a set of ontologies so they can be
used by the classifier's feature extractor.
"""
# WordNet : Pathogens
wordnet = {}
import nltk
def traverse_hyponyms(synset, depth=3):
    hyponym_dict = {}
    for syn in synset:
        d_r_lemmas = [syn]
        for lemma in syn.lemmas:
            d_r_lemmas.extend(lemma.derivationally_related_forms())
        lemmas = set([lemma.name.split('.')[0].replace('_', ' ') for lemma in d_r_lemmas])
        for lemma in lemmas:
            hyponym_dict[lemma] = lemmas
        if depth > 0:
            child_hyponym_dict = traverse_hyponyms(syn.hyponyms(), depth-1)
            for hypo, parents in child_hyponym_dict.items():
                parents |= lemmas
            hyponym_dict.update(child_hyponym_dict)
    return hyponym_dict
def exclude_keywords(keyword_map, excluded):
    return {
        k : v - excluded
        for k, v in keyword_map.items()
        if k not in excluded
    }
synset = nltk.wordnet.wordnet.synsets("pathogen")[0].hypernyms() + nltk.wordnet.wordnet.synsets("virus")
all_wn_pathogens = traverse_hyponyms(synset)
wordnet['pathogens'] = exclude_keywords(all_wn_pathogens, set(filter(lambda x: len(x) < 2, all_wn_pathogens)) | set(['computer virus']))
print len(wordnet['pathogens'])


# WordNet : Host names
# A lot of these are pretty farfetched. It would be a good idea to add some other sources for hosts.
import nltk
synset = nltk.wordnet.wordnet.synsets("insect")[:1] +    nltk.wordnet.wordnet.synsets("animal")[:1] +    nltk.wordnet.wordnet.synsets("mammal") +    nltk.wordnet.wordnet.synsets('plant')[1:2]

#Definately an incomplete list:
non_host_names = set(['sponge', 'pest', 'mate',
                      'big game', 'prey',
                      'young', 'worker', 'head',
                      'carnivore',
                      'dam',
                      'giant', 'world',
                      'medusa',
                      'simple',
                      'Neandertal',
                      'A', 'E', 'C'])
probably_not_host_names = set([
    'soldier',
    'pooch', 'kitten',
    'game',
    # We might miss disease carrying hawthorns because of this
    # however the false positive rate will cause bigger problems.
    'may',
    'mastodon',
    'lapdog', 'young bird',
    'young fish'
])
wordnet['hosts'] = exclude_keywords(traverse_hyponyms(synset), non_host_names | probably_not_host_names)
print len(wordnet['hosts'])
wordnet['hosts']


# WordNet : Seasons and Climate
# Some potential extensions for extracting season features:
# * Use season component from extracted dates
# * Use location to account for hemisphere differences interpreting season vocabulary.
wordnet['season'] = traverse_hyponyms([nltk.wordnet.wordnet.synsets("season")[1]] + 
                                      nltk.wordnet.wordnet.synsets("annual"))
wordnet['climate'] = traverse_hyponyms(nltk.wordnet.wordnet.synsets("weather")[:1])

modifiers = {
    "large" : traverse_hyponyms(nltk.wordnet.wordnet.synsets("massive") + nltk.wordnet.wordnet.synsets("large")),
    "severe" : traverse_hyponyms(nltk.wordnet.wordnet.synsets("dangerous")),
    "rare" : traverse_hyponyms(nltk.wordnet.wordnet.synsets("uncommon") + nltk.wordnet.wordnet.synsets("atypical")),
    "painful" : traverse_hyponyms(nltk.wordnet.wordnet.synsets("painful"))
}

# Symptoms and diseases
import bson
with open("portfolio_manager_tags.bson", 'rb') as f:
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
        #Remove long tags that we are unlikely to find
        if len(tag_name) > 30:
            continue
        if 'category' in tag:
            cat = tag['category']
            if cat in pm_keywords:
                pm_keywords[cat].add(tag_name)
            else:
                pm_keywords[cat] = set([tag_name])
    except:
        print 'Exception on tag:', tag
tag_blacklist = set(['can', 'don', 'dish', 'ad', 'mass', 'yellow'])

print "Portfolio Manager Keyword Counts:"
for cat, keywords in pm_keywords.items():
    print cat, ':', len(keywords)
print ""

pm_keywords['vector'].update({
    'rodent-borne' : set(['animal borne', 'animal-borne', 'animalborne']),
    'rodent borne' : set(['animal borne', 'animal-borne', 'animalborne']),
    'rodentborne'  : set(['animal borne', 'animal-borne', 'animalborne']),
    'animal-borne' : set(['animal borne', 'animalborne']),
    'animal borne' : set(['animal-borne', 'animalborne']),
    'animalborne' : set(['animal-borne', 'animal borne']),
})

pm_keywords['mode of transmission'].update({
    'droppings' : set(),
    'urine' : set(),
    'saliva' : set(),
})

pm_keywords['symptom'].update({
    'loss of memory' : set()
})

pm_keywords['mode of transmission'].update(traverse_hyponyms(nltk.wordnet.wordnet.synsets('inhale')))

pm_keywords['symptom'] -= tag_blacklist
pm_keywords['disease'] -= tag_blacklist
for cat, keywords in pm_keywords.items():
    pm_keywords[cat] = { k : set() for k in keywords }



# [The Disease ontology](http://disease-ontology.org/downloads/)
import rdflib
disease_ontology = rdflib.Graph()
disease_ontology.parse("http://purl.obolibrary.org/obo/doid.owl", format="xml")
# Many diseases have predicates like has_symptom listed as plain text in their definition, this code extracts them.
import re
def create_re_for_predicate(predicate):
    esc_pred = re.escape(predicate)
    return re.compile("(" +
        predicate +
        r" (?P<" + predicate + ">(.+?)))" +
        r"(,|\.|(\s(or|and|\w+\_\w+)))", re.I)

predicates = [
    "has_symptom",
    "transmitted_by",
    "has_material_basis_in",
    "results_in",
    "located_in"
]

doid_res = map(create_re_for_predicate, predicates)

def parse_doid_def(def_str):
    for doid_re in doid_res:
        for m in doid_re.finditer(def_str):
            yield m.groupdict()
            
def flatten(li):
    for subli in li:
        for it in subli:
            yield it
            
qres = disease_ontology.query("""
SELECT DISTINCT ?def
WHERE {
    BIND (<http://purl.obolibrary.org/obo/IAO_0000115> AS ?defined_as)
    BIND (<http://purl.obolibrary.org/obo/DOID_0050117> AS ?disease)
    ?subject rdfs:subClassOf* ?disease .
    ?subject ?defined_as ?def .
}
""")
grouped_disease_predicates = [list(parse_doid_def(unicode(r))) for r in qres]

predicate_value_sets = {
    predicate : set()
    for predicate in predicates
}

for disease_predicates in flatten(grouped_disease_predicates):
    for predicate, value in disease_predicates.items():
        predicate_value_sets[predicate].add(value)
doid_keywords = { k : list(v) for k,v in predicate_value_sets.items() }


# The disease ontology has synonyms for many diseases that are not in our disease keyword set.
# Furthermore, the subclass relationships in the disease ontology could help us
# as additional general category labels to the Health Map data for things like "primary bacterial infectious disease".
# Every disease is a class which seems strange to me,
# I think it is more natural to think of them as instances of classes.
# A number of subjects that appear to be diseases have no subClassOf predicate.
# They do however have inSubset predicates.
# The ones I spot checked have depricated predicates set to true, so I think we can ignore them.
# A few subjects have multiple subClassOf predicates.
import collections

class memoized(object):
    """
    Decorator. Caches a function's return value each time it is called.
    If called later with the same arguments, the cached value is returned
    (not reevaluated).
    """
    def __init__(self, func):
       self.func = func
       self.cache = {}
    def __call__(self, *args):
       if not isinstance(args, collections.Hashable):
          # uncacheable. a list, for instance.
          # better to not cache than blow up.
          return self.func(*args)
       if args in self.cache:
          return self.cache[args]
       else:
          value = self.func(*args)
          self.cache[args] = value
          return value
    def __repr__(self):
       '''Return the function's docstring.'''
       return self.func.__doc__
    def __get__(self, obj, objtype):
       '''Support instance methods.'''
       return functools.partial(self.__call__, obj)
    
def get_subject_to_label_dict(ontology):
    # Bidirectional symptom links could cause problems, so I'm avoiding them for now.
    qres = ontology.query("""
    SELECT ?subject ?label
    WHERE {
        { ?subject <http://www.geneontology.org/formats/oboInOwl#hasNarrowSynonym> ?label . } UNION
        { ?subject <http://www.geneontology.org/formats/oboInOwl#hasRelatedSynonym> ?label . } UNION
        { ?subject <http://www.geneontology.org/formats/oboInOwl#hasExactSynonym> ?label . } UNION
        { ?subject rdfs:label ?label . }
    }
    """)
    subject_to_labels = {}
    for subject, label in qres:
        subject = unicode(subject)
        label = unicode(label)
        if subject not in subject_to_labels:
            subject_to_labels[subject] = set()
        if '(' in label or ',' in label: continue
        subject_to_labels[subject].add(label)
    return subject_to_labels
def get_subject_to_parents_dict(ontology, root):
    qres = ontology.query("""
    SELECT ?subject ?parent
    WHERE {
        BIND (<%s> AS ?root)
        ?subject rdfs:subClassOf* ?root .
        ?subject rdfs:subClassOf ?parent .
    }
    """ % root)
    subject_to_parents = {}
    for subject, parent in qres:
        subject = unicode(subject)
        parent = unicode(parent)
        subject_to_parents[subject] = subject_to_parents.get(subject, []) + [parent]
    return subject_to_parents
    
def get_subject_to_ancestor_dict(subject_to_parents):
    @memoized
    def get_ancestors(subject):
        # The root's parent will not appear in subject_to_parents
        parents = subject_to_parents.get(subject, [])
        return set(parents + list(flatten([get_ancestors(p) for p in parents])))
    return { s : get_ancestors(s) for s in subject_to_parents.keys() }


def get_linked_keywords(ontology, root):
    """
    Get all the keywords (e.g. labels and synonyms) in an OBO ontology,
    and using the subclass predicate, link them to the labels/syns of
    ancestoral entities.
    """
    subject_to_labels = get_subject_to_label_dict(ontology)
    subject_to_parents = get_subject_to_parents_dict(ontology, root)
    #Filter out subjects without parents
    #And add fake labels for subjects that have parents
    split_uri = re.compile(r'#|/').split
    subject_to_labels = {k : subject_to_labels.get(k, set([split_uri(k)[-1]]))
                         for k in subject_to_parents.keys()}
    subject_to_ancestors = get_subject_to_ancestor_dict(subject_to_parents)
    for subject, ancestors in subject_to_ancestors.items():
        if root not in ancestors and subject != root:
            print subject, ancestors
            print subject_to_parents
            raise Exception("Root is not in ancestors")
        ancestors.remove(root)
    keywords = {}
    for subject, labels in subject_to_labels.items():
        all_ancestors = set(flatten(map(subject_to_labels.get, subject_to_ancestors[subject])))
        for lab in labels:
            if lab in keywords:
                # print "Label already in keywords: ", lab
                keywords[lab] |= all_ancestors | labels
            else:
                keywords[lab] = all_ancestors | labels
    return keywords

doid_keywords['diseases'] = get_linked_keywords(disease_ontology, "http://purl.obolibrary.org/obo/DOID_4")
print len(doid_keywords['diseases'])


# [Symptom Ontology](http://purl.obolibrary.org/obo/ido.owl)
symptom_ontology = rdflib.Graph()
symptom_ontology.parse("http://purl.obolibrary.org/obo/symp.owl", format="xml")

symp_keywords = {}
symp_keywords['symptoms'] = get_linked_keywords(symptom_ontology, "http://purl.obolibrary.org/obo/SYMP_0000462")
print "Symptoms in the symptom ontology:", len(symp_keywords['symptoms'])

# [The Infectious Disease Ontology](http://www.ontobee.org/browser/index.php?o=IDO)
# I haven't found much of use in this ontology.
# It seems more oriented toward higher level reasoning than providing taxonomies and synsets.
# ido = rdflib.Graph()
# ido.parse("http://purl.obolibrary.org/obo/ido.owl", format="xml")


# [Biocaster ontology](https://code.google.com/p/biocaster-ontology/downloads/detail?name=BioCaster2010-30-Aug-904.owl&can=2&q=)
import rdflib
g = rdflib.Graph()
g.parse("https://biocaster-ontology.googlecode.com/files/BioCaster2010-30-Aug-904.owl", format="xml")

# The ontology is composed of subject-relationship-object triples.
# For example: `("Python", "is a", "programming language")`
# I think one of the particularly interesting things about biocaster is that they are using these relationships for diagnosis.
# For example:
# 
# `http://biocaster.nii.ac.jp/biocaster#FeverSymptomHuman_4447 http://biocaster.nii.ac.jp/biocaster#indicates http://biocaster.nii.ac.jp/biocaster#DISEASE_491`


# Symptoms

qres = g.query("""
SELECT DISTINCT ?label
WHERE {
    ?subject rdfs:subClassOf* biocaster:SYMPTOM .
    ?instance a ?subject .
    ?instance biocaster:synonymTerm ?synonym .
    ?synonym rdfsn:type biocaster:englishTerm .
    ?synonym biocaster:label ?label
}
""", initNs={
    'biocaster': rdflib.URIRef("http://biocaster.nii.ac.jp/biocaster#"),
    'rdfsn': rdflib.URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
})
biocaster_symptom_syns = [row[0] for row in qres]

# Diseases

qres = g.query("""
SELECT DISTINCT ?label
WHERE {
    ?subject rdfs:subClassOf* biocaster:DISEASE .
    ?instance a ?subject .
    ?instance biocaster:synonymTerm ?synonym .
    ?synonym rdfsn:type biocaster:englishTerm .
    ?synonym biocaster:label ?label
}
""", initNs={
    'biocaster': rdflib.URIRef("http://biocaster.nii.ac.jp/biocaster#"),
    'rdfsn': rdflib.URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
})
biocaster_disease_syns = [row[0] for row in qres]

# Pathogens

qres = g.query("""
SELECT DISTINCT ?label
WHERE {
    { ?subject rdfs:subClassOf* biocaster:BACTERIUM } UNION
    { ?subject rdfs:subClassOf* biocaster:VIRUS } UNION
    { ?subject rdfs:subClassOf* biocaster:FUNGUS } UNION
    { ?subject rdfs:subClassOf* biocaster:PROTOZOAN } .
    ?instance a ?subject .
    ?instance biocaster:synonymTerm ?synonym .
    ?synonym rdfsn:type biocaster:englishTerm .
    ?synonym biocaster:label ?label
}
""", initNs={
    'biocaster': rdflib.URIRef("http://biocaster.nii.ac.jp/biocaster#"),
    'rdfsn': rdflib.URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
})
biocaster_pathogen_syns = [row[0] for row in qres]

biocaster_keywords = {
    'symptoms':set([re.sub(r" \(.*\)", "", unicode(s)) for s in biocaster_symptom_syns]),
    'diseases':set([unicode(s).strip() for s in biocaster_disease_syns]),
    'pathogens':set([unicode(s).strip() for s in biocaster_pathogen_syns]),
}

# [Terrain](http://cegis.usgs.gov/ontology.html#constructing_ontologies)
# This keyword set is used to capure environmental factors. For example,
# a disease might be related to swamps or cities with high populations density.
terrain_ontology = rdflib.Graph()
terrain_ontology.parse("http://usgs-ybother.srv.mst.edu/ontology/vocabulary/Event.n3", format="n3")
terrain_ontology.parse("http://usgs-ybother.srv.mst.edu/ontology/vocabulary/Division.n3", format="n3")
#Not sure why I can't parse this. It might be RDFLib: https://github.com/RDFLib/rdflib/issues/379
#terrain_ontology.parse("http://usgs-ybother.srv.mst.edu/ontology/vocabulary/BuiltUpArea.n3", format="n3")
terrain_ontology.parse("http://usgs-ybother.srv.mst.edu/ontology/vocabulary/EcologicalRegime.n3", format="n3")
terrain_ontology.parse("http://usgs-ybother.srv.mst.edu/ontology/vocabulary/SurfaceWater.n3", format="n3")
terrain_ontology.parse("http://usgs-ybother.srv.mst.edu/ontology/vocabulary/Terrain.n3", format="n3")
usgs_keywords = {}
usgs_keywords['terrain'] = get_linked_keywords(terrain_ontology, "http://www.w3.org/2002/07/owl#Thing")


# Export

def squash_dict(d, delimiter='/', crunch=False, layers=-1):
    """
    Combine recursively nested dicts into the top level dict by prefixing their
    keys with the top level key and delimiter.
    Use the layers parameter to limit the recursion depth.
    Adding the prefixed keys could collide with keys already in the
    top level dictionary, use crunch to suppress errors and replace the
    top level keys when this happens.
    """
    dout = {}
    for k, v in d.items():
        if isinstance(v, dict) and layers != 0:
            for vk, vv in squash_dict(v, delimiter, crunch, layers - 1).items():
                new_key = k + delimiter + vk
                if not crunch and new_key in d.keys():
                    raise Exception("Collision when squashing dict.")
                dout[new_key] = vv
        else:
            dout[k] = v
    return dout

import json
import re
wordnet.update(squash_dict({ 'mod' : modifiers}, layers=1))
keywords = squash_dict({
    'wordnet' : wordnet,
    'pm' : pm_keywords,
    'biocaster' : biocaster_keywords,
    'doid' : doid_keywords,
    'symp' : symp_keywords,
    'usgs' : usgs_keywords
}, layers=1)
import pickle
with open('ontologies.p', 'wb') as f:
    pickle.dump(keywords, f)

print "Total keywords:", len(set(flatten(keywords.values())))

# aws s3 cp ontologies.p s3://classifier-data/ --region us-west-1
