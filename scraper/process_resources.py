import goose
from bs4 import BeautifulSoup
import random
import ctypes
import concurrent.futures
import os, json
import readability
import lxml

def extract_clean_content(content):
    # I found out about goose and readability here:
    # http://stackoverflow.com/questions/14164350/identifying-large-bodies-of-text-via-beautifulsoup-or-other-python-based-extract
    # The poster seems to like goose more.
    # One difference is that goose cleans up all the html, while readability
    # usually just remove cruft that isn't related to the article text.
    # There is a trade off between retaining links and formatting, and
    # getting cleaner text.
    # For now, we're using goose for simplicity.
    
    ###### Readability code:
    readability_error = None
    result = {}
    try:
        document = readability.readability.Document(content)
        content = document.summary()
    except readability.readability.Unparseable as e:
        readability_error = '\n'.join([str(i) for i in sys.exc_info()])
    except (lxml.etree.XMLSyntaxError,
            lxml.etree.DocumentInvalid,
            lxml.etree.ParserError) as e:
        readability_error = '\n'.join([str(i) for i in sys.exc_info()])
    except (AttributeError, ValueError, TypeError) as e:
        # This ought to be handled by readability.
        readability_error = '\n'.join([str(i) for i in sys.exc_info()])
    if readability_error:
        print readability_error
    #########
    
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
    # if len(cleaned_content) < 50:
    #     # Most of the articles with content this short don't
    #     # have any content we would want to extract.
    #     return None
    return cleaned_content
