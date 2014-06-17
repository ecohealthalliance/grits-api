import goose
from bs4 import BeautifulSoup
import random
import ctypes
import concurrent.futures
import os, json

def resource_url(id, set_name="train"):
    if isinstance(id, dict):
        id = id['_id']
    import git
    r = git.Repo(os.path.dirname(__file__))
    return "https://github.com/ecohealthalliance/corpora/blob/" +\
        r.active_branch + "/healthmap/" + set_name + "/" + id + ".md"

def filter_exceptions(resources):
    """
    The unscrapable resources and resources we couldn't extract articles from
    create exception objects that
    that need to be filtered out of the resource array.
    """
    resources_out, exceptions = [], []
    for resource in resources:
        if isinstance(resource, dict):
            resources_out.append(resource)
        else:
            exceptions.append(resource)
    return resources_out, exceptions

def translations_to_dict(translation_roa):
    translations = {}
    for translation in translation_roa:
        translations[translation['id']] = translation['translation']
    return translations

def fetch_translations(path):
    translations = []
    for root, dirs, files in os.walk(path):
        for file_name in files:
            if not file_name.endswith('.json'): continue 
            file_path = os.path.join(root, file_name)
            with open(file_path) as f:
                translations.extend(json.load(f))
    assert len(translations) > 0
    return translations_to_dict(translations)
    
def attach_translations(resources):
    global translations
    if not translations:
        translations = fetch_translations(os.path.join(os.path.dirname(__file__), 'translations'))
    for resource in resources:
        if resource['_id'] in translations:
            resource['cleanContent'] = translations[resource['_id']]
            resource['translated'] = True
    return resources

def extract_clean_content(content):
    if not content.startswith('<html>'):
        content = '<html><body>' + content + '</body></html>'
    try:
        cleaned_content = goose.Goose({
            'parser_class':'soup',
            'enable_image_fetching' : False,
        }).extract(raw_html=content).cleaned_text
    except ValueError:
        cleaned_content = ''
    if len(cleaned_content) < 1:
        # Goose doesn't do well with foreign language content.
        # If we can't find content with goose try extracting
        # all the text with Beautiful soup.
        # Beautiful soup doesn't attempt to extract the article,
        # it just finds all the text in the html, which seems to be
        # good enough since we've already used readability on the articles.
        cleaned_content = BeautifulSoup(content).text
    if len(cleaned_content) < 50:
        # Most of the articles with content this short don't
        # have any content we would want to extract.
        return None
    return cleaned_content

class PreprocessException(Exception):
    pass

def preprocess_resource(resource):
    if resource.get('translated'): return resource
    cleaned_content = get_clean_content(resource.get('content'))
    if clean_content:
        return cleaned_content
    else:
        raise PreprocessException()
    
def process_resource(resource):
    try:
        return preprocess_resource(resource)
    except PreprocessException as e:
        return e

def process_resources(resources):
    """
    This creates copies of resources,
    but might mutate them in some cases.
    """
    with concurrent.futures.ProcessPoolExecutor() as executor:
        for resource in executor.map(process_resource, resources):
            yield resource
