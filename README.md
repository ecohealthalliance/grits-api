GRITS API Set-up
================

From the directory you clone this repository into do the following:

    # create a config file
    cp config.sample.py config.py
    pico config.py
    # set up a virtual env
    sudo pip install virtualenv virtualenvwrapper
    export WORKON_HOME=~/Envs
    source /usr/local/bin/virtualenvwrapper.sh
    mkvirtualenv grits_api_env
    # create directories for logging
    mkdir celery
    mkdir supervisord
    # Some system packages that will be required
    sudo apt-get install libapache2-mod-wsgi lib32z1-dev mongodb-server
    sudo apt-get install zip unzip
    # Import geonames for the location extractor
    ./import-geonames.sh
    # This script does the rest. Rerun it to update when the code changes.
    ./deploy.sh

Testing
=======

To run the tests:

    git clone -b fetch_4-18-2014 git@github.com:ecohealthalliance/corpora.git
    cd test
    python -m unittest discover

Many tests are based on the comments in this document:
https://docs.google.com/document/d/12N6hIDiX6pvIBfr78BAK_btFxqHepxbrPDEWTCOwqXk/edit
