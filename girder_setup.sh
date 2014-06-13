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


