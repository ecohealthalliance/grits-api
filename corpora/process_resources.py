import goose
from bs4 import BeautifulSoup
import random
import ctypes
import concurrent.futures
import os, json
import translation

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

def attach_translations(resources):
    return translation.attach_translations(resources)

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
    cleaned_content = extract_clean_content(resource.get('content'))
    if cleaned_content:
        resource['cleanContent'] = cleaned_content
        return resource
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
