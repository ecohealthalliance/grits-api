#!/bin/bash

# configuration variables to set:

# GIRDER_INSTALL_PATH
# the path where girder will be cloned
# the user running this script should have write permissions

# APACHE_URL
# the root URL of the apache server, i.e.
# https://grits.ecohealth.io

# GIRDER_MOUNT_PATH
# the url path where girder is mounted
: ${GIRDER_MOUNT_PATH=/gritsdb}

# GIRDER_DEPLOYMENT_MODE
# 'production' or 'development', default to production:
: ${GIRDER_DEPLOYMENT_MODE=production}

# GIRDER_SOCKET_HOST
# host that girder will listen on
# default to local only
: ${GIRDER_SOCKET_HOST=127.0.0.1}

# GIRDER_SOCKET_PORT
# port that girder will listen on
# default to 9999
: ${GIRDER_SOCKET_PORT=9999}

# GIRDER_ADMIN_PASSWORD
# the password to set for the girder admin
# the user name for this account will be 'grits'

# GIRDER_ADMIN_EMAIL
# the email address for the girder admin account

# HEALTHMAP_APIKEY
# the api key for healthmap access

# capture the path to this script
pushd `dirname $0` &> /dev/null
script_path=`pwd -P`
popd &> /dev/null

# go to the deployment directory
mkdir -p "${GIRDER_INSTALL_PATH}" &> /dev/null  # make the path if necessary
cd "${GIRDER_INSTALL_PATH}"

# clone girder from git
git clone https://github.com/girder/girder.git

# go to the plugins subdirectory
cd girder/plugins

# clone the grits plugin
git clone https://github.com/ecohealthalliance/gritsSearch.git

# go up to the main girder directory
cd ..

# create a new virtualenv for girder deps
virtualenv girder_env
. girder_env/bin/activate

# install python dependencies
pip install --requirement requirements.txt

# install other python deps
pip install requests python-dateutil

# install grunt
npm install grunt-cli

# set a variable to /path/to/grunt
export grunt="${PWD}/node_modules/.bin/grunt"

# install node dependencies
npm install

# configure the server:
cat > girder/conf/girder.local.cfg <<EOF
[global]
server.socket_host: "${GIRDER_SOCKET_HOST}"
server.socket_port: ${GIRDER_SOCKET_PORT}
tools.proxy.on: True
tools.proxy.base: "${APACHE_URL}${GIRDER_MOUNT_PATH}"
tools.proxy.local: ""

[server]
mode: "${GIRDER_DEPLOYMENT_MODE}"
api_root: "${GIRDER_MOUNT_PATH}/api/v1"
static_root: "${GIRDER_MOUNT_PATH}/gritsdb/static"
EOF

# build the source
"${grunt}" init && "${grunt}"

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

url = '${APACHE_URL}${GIRDER_MOUNT_PATH}/api/v1'

passwd = '${GIRDER_ADMIN_PASSWORD}'

# do initialization of girder for healthmap import
# create main grits user
resp = requests.post(
    url + '/user',
    params={
        'login': 'grits',
        'password': passwd,
        'firstName': 'grits',
        'lastName': 'grits',
        'email': '${GIRDER_ADMIN_EMAIL}'
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
# it suffices just to touch the config file
touch girder/conf/girder.local.cfg

# now hit the grits api to initialize the database
curl "${APACHE_URL}${GIRDER_MOUNT_PATH}/api/v1/resource/grits" &> /dev/null

# At this point everything is ready to start importing the healthmap data.
# To import the last day, use the script in this repo `healthMapGirder.py`:

# python healthMapGirder.py --day

# for a full two year import:

# python healthMapGirder.py --full

# To run the script automatically every day, you can create a script in /etc/cron.daily.
# (make sure the script name does not contain any '.' characters, otherwise cron will
# ignore them.  This is what I did for grits.ecohealth.io:

cat > "${GIRDER_INSTALL_PATH}/girder/hmapImportDay" <<EOF
#!/bin/bash

. girder_env/bin/activate"
export HEALTHMAP_APIKEY="${HEALTHMAP_APIKEY}"
python healthMapGirder.py --twoday
EOF
chmod +x "${GIRDER_INSTALL_PATH}/girder/hmapImportDay"
echo "0 1 * * * cd \"${GIRDER_INSTALL_PATH}/girder\" && ./hmapImportDay" | crontab -

# This runs a two day import every day just to make sure it gets the full days data.
