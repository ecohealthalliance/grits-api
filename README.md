GRITS API Set-up
================

These instructions were tested on a Ubuntu 14.04 LTS 64bit AWS Instance.
They assume you cloned this repository and this readme is in your current directory.

Install and start Mongo:

Script based on these [instructions](http://docs.mongodb.org/manual/tutorial/install-mongodb-on-linux/)

    cd ~
    curl -O http://downloads.mongodb.org/linux/mongodb-linux-x86_64-2.6.2.tgz
    tar -zxvf mongodb-linux-x86_64-2.6.2.tgz
    mkdir -p mongodb
    cp -R -n mongodb-linux-x86_64-2.6.2/ mongodb
    echo 'export PATH=~/mongodb/mongodb-linux-x86_64-2.6.2/bin/:$PATH' | tee -a ~/.bashrc
    source ~/.bashrc
    mkdir -p ~/data/db
    mongod --fork --logpath ~/mongodb.log --dbpath ~/data/db

Install these packages:

    sudo apt-get install git make python-pip python-dev
    sudo apt-get install gfortran libopenblas-dev liblapack-dev
    sudo apt-get install lib32z1-dev zip unzip libxml2-dev libxslt1-dev
    # libffi is for girder setup, should move to girder script
    sudo apt-get install libffi-dev
    
Set-up girder:

    # Install the AWS CLI as sudo so it is available in all environments.
    sudo pip install awscli
    # Configure it with your account details:
    mkdir ~/.aws
    tee ~/.aws/config <<EOF
    [default]
    region = us-east-1
    aws_access_key_id = AKIAIJMXFI2GUJB66FXA
    aws_secret_access_key = Iy2K/b6aClpWutZh/JlCoguY8FhNdO+QFVrrl4sF
    EOF
    # To download the database dump from S3:
    aws s3 cp --recursive s3://girder-data/dump dump
    mongorestore
    APACHE_URL=http://grits.ecohealth.io HEALTHMAP_APIKEY=123ABC GIRDER_ADMIN_PASSWORD=password ./girder_setup.sh
    # If you want to automatically backup the database use the following commands:
    tee ~/dump_girder_to_s3 <<EOF
    #!/bin/bash
    mongodump --db girder
    aws s3 cp --recursive dump s3://girder-data/dump
    echo "dump completed on `date`"
    EOF
    chmod +x dump_girder_to_s3
    # (crontab -l ; echo "0 1 * * * cd ~ && ./dump_girder_to_s3 > dump_to_s3_log") | crontab

From the directory you cloned this repository into do the following:

    cd grits-api
    # create a config file
    cp config.sample.py config.py
    pico config.py
    # set up a virtual env
    sudo pip install virtualenv virtualenvwrapper
    echo 'export WORKON_HOME=~/Envs' | tee -a ~/.bashrc
    echo 'source /usr/local/bin/virtualenvwrapper.sh' | tee -a ~/.bashrc
    source ~/.bashrc
    mkvirtualenv grits_api_env
    # create directory for logging
    mkdir supervisord
    pip install -r requirements.txt
    supervisord -c supervisord.conf
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
