#!/bin/bash
wget http://download.geonames.org/export/dump/allCountries.zip
unzip allCountries.zip -d diagnosis
rm allCountries.zip
cd diagnosis && python mongo_import_geonames.py
rm allCountries.txt
cd ..
