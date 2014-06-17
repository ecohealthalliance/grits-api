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
    sudo apt-get install lib32z1-dev zip unzip libxml2-dev libxslt1-dev
    pip install -r requirements.txt
    supervisord -c supervisord.conf
    # Install mongodb if it's not present
    # sudo apt-get install mongodb-server
    # Import geonames for the location extractor
    ./import_geonames.sh
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
