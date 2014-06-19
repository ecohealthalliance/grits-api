#!/bin/bash

# go to the deployment directory, for example:
# cd /opt

# clone girder from git
git clone https://github.com/girder/girder.git

# go to the plugins subdirectory
cd girder/plugins

# clone the grits plugin
git clone https://github.com/ecohealthalliance/gritsSearch.git

# go up to the main girder directory
cd ..

# install python dependencies
pip install --requirement requirements.txt

# install other python deps
pip install requests python-dateutil

# install grunt globally (or modify $PATH)
npm install -g grunt

# install node dependencies
npm install

# configure the server:
cat > girder/conf/girder.local.cfg <<EOF
[global]
server.socket_host: "0.0.0.0"
server.socket_port: 9999
tools.proxy.on: True
tools.proxy.base: "https://grits.ecohealth.io/gritsdb"
tools.proxy.local: ""

[server]
# Set to "production" or "development"
mode: "development"
api_root: "/gritsdb/api/v1"
static_root: "/gritsdb/static"
EOF

# build the source
grunt init && grunt

# create a startup script
# (this could be handled better with an actual init script)
cat > start_girder.sh <<EOF
#!/bin/bash

# girder tries to restart and crashes when a file changes
# so we put it into a loop and reload when that happens
while true ; do
    python -m girder
done
EOF
chmod +x start_girder.sh

# add startup script for example in /etc/rc.local:
# cd /opt/girder && ./start_girder.sh &

# start up girder now
./start_girder.sh &

# either start up girder in a browser or run the following
# to create the grits user and enable the grits plugin
python <<EOF
import requests

url = 'https://grits.ecohealth.io/gritsdb/api/v1'

passwd = 'rtKUQynf'  # should be changed

# do initialization of girder for healthmap import
# create main grits user
resp = requests.post(
    url + '/user',
    params={
        'login': 'grits',
        'password': passwd,
        'firstName': 'grits',
        'lastName': 'grits',
        'email': 'grits@not-an-email.com'
    },
    verify=False
)

# login as grits user (or as an admin)
resp = requests.get(
    url + '/user/authentication',
    auth=('grits', passwd),
    verify=False
)

token = resp.json()['authToken']['token']

# enable grits plugin
resp = requests.put(
    url + '/system/plugins',
    params={
        'plugins': '["grits"]',
        'token': token
    }
)
EOF

# now we have to restart girder to enable the plugin
kill %1
./start_girder.sh &

# now hit the grits api to initialize the database
curl https://grits.ecohealth.io/gritsdb/api/v1/resource/grits

# At this point everything is ready to start importing the healthmap data.
# To import the last day, use the script in this repo `healthMapGirder.py`:

# PYTHONPATH=/opt/girder HEALTHMAP_APIKEY=<put api key here> python healthMapGirder.py --day

# for a full two year import:

# PYTHONPATH=/opt/girder HEALTHMAP_APIKEY=<put api key here> python healthMapGirder.py --full

# To run the script automatically every day, you can create a script in /etc/cron.daily.
# (make sure the script name does not contain any '.' characters, otherwise cron will
# ignore them.  This is what I did for grits.ecohealth.io:

cat > /etc/cron.daily/hmapImportDay <<EOF
#!/bin/bash

cd /home/ubuntu/healthMap
HEALTHMAP_APIKEY=<...> PYTHONPATH=/opt/girder python healthMapGirder.py --twoday &> /var/log/hmapLastImport.log
EOF
chmod +x /etc/cron.daily/hmapImportDay

# This runs a two day import every day just to make sure it gets the full days data.
