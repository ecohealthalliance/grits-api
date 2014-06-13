#!/bin/bash
export WORKON_HOME=~/Envs
source /usr/local/bin/virtualenvwrapper.sh
workon grits_api_env
pip install -r requirements.txt
python deploy_helper.py
python train.py
supervisorctl update
supervisorctl restart celery flask
deactivate