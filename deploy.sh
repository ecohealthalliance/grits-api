#!/bin/bash
workon venv
pip install -r requirements.txt
python deploy.py
python train.py
supervisorctl update
supervisorctl restart celery
detach
