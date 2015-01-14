"""
This script has functions for detecting english text and
reading translations stored in csv files.
"""
import re
import os
import json
import logging
import microsofttranslator
import datetime
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

class Translator(object):
    def __init__(self, config):
        self.config = config
        self.stored_translations = None
        self.consecutive_exceptions = 0
        
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
        
    def __translations_to_dict(self, translation_roa):
        translations = {}
        for translation in translation_roa:
            translations[translation['id']] = translation['translation']
        return translations

    def __fetch_translations(self, path):
        translations = []
        if os.path.exists(path):
            for root, dirs, files in os.walk(path):
                for file_name in files:
                    if not file_name.endswith('.json'): continue 
                    file_path = os.path.join(root, file_name)
                    with open(file_path) as f:
                        translations.extend(json.load(f))
        if len(translations) == 0:
            logger.warn("No translations were fetched!")
        return self.__translations_to_dict(translations)

    def get_translation(self, id):
        if not self.stored_translations:
            self.stored_translations = self.__fetch_translations(
                os.path.join(os.path.dirname(__file__), 'translations'))
        return self.stored_translations.get(id)

    def translate_to_english(self, content):
        if self.consecutive_exceptions > 4:
            # Back off when we reach more than 4 consecutive exceptions
            # because we probably hit the api limit.
            return {
                'error' : 'Too many consecutive exceptions'
            }

        try:
            translation_api = microsofttranslator.Translator(
                self.config.bing_translate_id,
                self.config.bing_translate_secret)
            translation = translation_api.translate(content, 'en')
            if translation.startswith("TranslateApiException:"):
                raise microsofttranslator.TranslateApiException(
                    translation.split("TranslateApiException:")[1])
            return {
                'content' : translation,
                'translationDate' : datetime.datetime.now(),
                'translationService' : 'microsoft'
            }
            self.consecutive_exceptions = 0
        except microsofttranslator.TranslateApiException as e:
            self.consecutive_exceptions += 1
            return {
                'error' : unicode(e),
                'consecutive_exceptions' : self.consecutive_exceptions
            }
        except ValueError as e:
            # Some articles (e.g. 532c9a3af99fe75cf5383290)
            # trigger value errors in the microsofttranslator code
            # during JSON parsing.
            self.consecutive_exceptions += 1
            return {
                'error' : unicode(e),
                'consecutive_exceptions' : self.consecutive_exceptions
            }
