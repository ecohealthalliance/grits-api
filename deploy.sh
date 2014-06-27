#!/bin/bash
grits_api_env/bin/pip install -r requirements.txt
grits_api_env/bin/python <<EOF
import nltk
nltk.download([
    'maxent_ne_chunker',
    'maxent_treebank_pos_tagger',
    'words',
    'punkt'
])
EOF
grits_api_env/bin/python train.py
sudo supervisorctl restart celery celery_batch_workers flask
