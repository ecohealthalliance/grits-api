"""
This script will create CSVs that we can use to create
resources translations. In the long run we should pay to use a translation API
that is built into a processing pipeline (which will probably cost 1-2 cents an article).
"""
import argparse
import goose
import unicodecsv
import datetime
import random
from bs4 import BeautifulSoup
import re
import os
import json
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

most_common_english_words = [
'the','be','to','of','and',
#'a', espanol
'in',
'that',
'have',
'I',
'it',
'for',
'not',
'on',
'with',
'he',
'as',
'you',
'do',
'at',
'this',
'but',
'his',
'by',
'from',
'they',
'we',
'say',
'her',
'she',
'or',
'an',
'will',
'my',
'one',
'all',
'would',
'there',
'their',
'what',
'so',
'up',
'out',
'if',
'about',
'who',
'get',
'which',
'go',
'me',
'when',
'make',
'can',
'like',
'time',
#'no', espanol
'just',
'him',
'know',
'take',
'people',
'into',
'year',
'your',
'good',
'some',
'could',
'them',
'see',
'other',
'than',
'then',
'now',
'look',
'only',
'come',
'its',
'over',
'think',
'also',
'back',
'after',
'use',
'two',
'how',
'our',
'work',
'first',
'well',
'way',
'even',
'new',
'want',
'because',
'any',
'these',
'give',
'day',
'most',
'us']
common_english_re = re.compile('\\b(' + '|'.join(most_common_english_words) + ')\\b', re.I)
def is_english(text):
    unique_matches = set()
    total_matches = 0
    required_unique_matches = min(5, len(text) / 100)
    required_matches = len(text) / 100
    for match in common_english_re.finditer(text):
        total_matches += 1
        if match.group(0) in unique_matches:
            continue
        else:
            unique_matches.add(match.group(0))
        if len(unique_matches) > required_unique_matches and total_matches > required_matches:
            return True
    return False

def batcher(li, batch_size=4000):
    batch = []
    for it in li:
        batch.append(it)
        if len(batch) == batch_size:
            yield batch
            batch = []
    yield batch

def translations_to_dict(translation_roa):
    translations = {}
    for translation in translation_roa:
        translations[translation['id']] = translation['translation']
    return translations

def fetch_translations(path):
    translations = []
    if os.path.exists(path):
        for root, dirs, files in os.walk(path):
            for file_name in files:
                if not file_name.endswith('.json'): continue 
                file_path = os.path.join(root, file_name)
                with open(file_path) as f:
                    translations.extend(json.load(f))
    if len(translations) == 0:
        logger.warn("No stored translations were loaded from the file system. " +
            "(This is a legacy feature for loading old translation into the database. " +
            "Unless that's what you're trying to do, don't worry about this warning.)")
    return translations_to_dict(translations)

translations = None

def attach_translations(resources):
    global translations
    if not translations:
        translations = fetch_translations(os.path.join(os.path.dirname(__file__), 'translations'))
    for resource in resources:
        if resource['_id'] in translations:
            resource['cleanContent'] = translations[resource['_id']]
            resource['translated'] = True
    return resources

def get_translation(id):
    global translations
    if not translations:
        translations = fetch_translations(os.path.join(os.path.dirname(__file__), 'translations'))
    return translations.get(id)

if __name__ == "__main__":
    from iterate_resources import iterate_resources
    from process_resources import process_resources, attach_translations, resource_url
    parser = argparse.ArgumentParser()
    parser.add_argument('-path', default='healthmap')
    parser.add_argument('-out', default='to_be_translated')
    args = parser.parse_args()
    start = datetime.datetime.now()
    count = 0
    resources = list(iterate_resources(args.path))
    processed_resources = process_resources(attach_translations(resources))
    non_english_resources = [r for r in processed_resources if isinstance(r, dict) and not is_english(r['cleanContent'])]
    for r in non_english_resources:
        if r.get('translated'):
            print "Translated article that still appears to be non-English:"
            print resource_url(r)
            print r['cleanContent']
    for idx, batch in enumerate(batcher(non_english_resources)):
        with open(os.path.join(args.out, 'texts.' + str(idx) + '.csv'), 'wb') as f:
            writer = unicodecsv.writer(f, encoding='utf-8')
            for resource in batch:
                if random.random() < 0.02:
                    print count, "resource files iterated over so far..."
                writer.writerow([resource['_id'], resource['cleanContent']])
                count += 1
    print "Non-English Resources:", count
    print "Time: ", datetime.datetime.now() - start
