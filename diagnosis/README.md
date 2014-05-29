Location Extractor
==================

To use the location extractor it is necessairy to download the geonames
allCountries dataset and import it into a mongodb instance:

    sudo apt-get install mongodb-server
    wget http://download.geonames.org/export/dump/allCountries.zip
    unzip allCountries.zip
    python mongo_import_geonames.py

I'm using Mongo to import geonames because it is too big to fit in a python dictionary array,
and the $in operator provides a fast way to search for all the ngrams in a document.

NLTK Dependencies:

    nltk.download([
        'maxent_ne_chunker',
        'maxent_treebank_pos_tagger',
        'words',
        'punkt'
    ])