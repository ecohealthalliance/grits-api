#!/bin/bash
wget http://download.geonames.org/export/dump/allCountries.zip
unzip allCountries.zip -d diagnosis
rm allCountries.zip
python diagnosis/mongo_import_geonames.py
