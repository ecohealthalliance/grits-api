"""
This contains any python code that needs to run during deployment.
"""
import nltk
nltk.download([
    'maxent_ne_chunker',
    'maxent_treebank_pos_tagger',
    'words',
    'punkt'
])
