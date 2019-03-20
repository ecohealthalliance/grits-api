"""
This script has functions for detecting english text and translating
text to english using a translation service.
"""
from __future__ import absolute_import
from __future__ import print_function
import re
import os
import datetime
from googleapiclient.errors import Error as GoogleAPIError
from googleapiclient.discovery import build
import requests

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

translate_key = os.environ.get('GOOGLE_TRANSLATE_KEY')

class Translator(object):
    def __init__(self):
        self.consecutive_exceptions = 0
        if translate_key:
            self.t_service = build('translate', 'v2', developerKey=translate_key)

    def is_english(self, text):
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

    def translate_to_english_google(self, content):
        if not translate_key:
            return {
                'error' : 'The translation service is not configured.'
            }
        if self.consecutive_exceptions > 4:
            # Stop using the API after several consecutive exceptions because
            # we probably hit the api limit or something is misconfigured.
            return {
                'error' : 'Translation has been disabled due to errors when attempting to access the tranlation service.'
            }
        try:
            result = self.t_service.translations().list(
              target='en',
              q=content
            ).execute()
            if ('translations' not in result or
                len(result['translations']) < 1 or
                'translatedText' not in result['translations'][0]):
                self.consecutive_exceptions += 1
                print("Unexpected Translation API response:", result)
                return {
                    'error' : 'Unexpected response from translation API.',
                    'consecutive_exceptions' : self.consecutive_exceptions
                }
            translation = result['translations'][0]['translatedText']
            self.consecutive_exceptions = 0
            return {
                'content' : translation,
                'translationDate' : datetime.datetime.now(),
                'translationService' : 'google'
            }
        except GoogleAPIError as e:
            self.consecutive_exceptions += 1
            return {
                'error' : str(e),
                'consecutive_exceptions' : self.consecutive_exceptions
            }

    def translate_to_english_ms(self, content):
        ms_translate_key = os.environ.get("MS_TRANSLATE_KEY")
        if not ms_translate_key:
            return {
                'error' : 'Microsoft translate key is missing.'
            }
        if self.consecutive_exceptions > 4 and (datetime.datetime.now() - self.last_failure).total_seconds() < 60 * 60 * 12:
            # Stop using the API after several consecutive exceptions because
            # we probably hit the api limit or something is misconfigured.
            return {
                'error' : 'Translation has been temporarily disabled due to errors when attempting to access the tranlation service.'
            }
        try:
            full_text = ""
            url = "https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&to=en"
            # Break text into 5000 character chunks to stay under api limit
            for section, noop in re.findall(r"(.{1,5000}(\s|$))", content, re.M | re.DOTALL):
                response = requests.post(url, headers={
                    "Ocp-Apim-Subscription-Key": ms_translate_key,
                    "Content-type": "application/json",
                }, json=[{
                    "Text" : section.encode("utf-8"),
                }])
                resp_json = response.json()
                resp_text = resp_json[0]["translations"][0]["text"]
                full_text += resp_text
            self.consecutive_exceptions = 0
            return {
                'content' : full_text,
                'translationDate' : datetime.datetime.now(),
                'translationService' : 'MS'
            }
        except Exception as e:
            self.consecutive_exceptions += 1
            self.last_failure = datetime.datetime.now()
            return {
                'error' : str(e),
                'consecutive_exceptions' : self.consecutive_exceptions
            }

    def translate_to_english(self, content):
        return self.translate_to_english_ms(content)
