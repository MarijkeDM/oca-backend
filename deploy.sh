#!/usr/bin/env bash
set -e
deploy_type=$1
if [ -z ${deploy_type} ]; then
deploy_type="google"
fi

if [ `git rev-parse --abbrev-ref HEAD` != "master" ]; then
  echo 'You can only deploy master';
#  exit 1
fi

CUR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_COLOR="\033[1;34m\n\n"
ERR_COLOR="\033[1;31m\n\n"
NO_COLOR="\n\033[0m"

pushd ${CUR_DIR}

bash install.sh

if [ ${deploy_type} = "google" ]; then
    echo -e "${LOG_COLOR}* Deploying to Google Cloud${NO_COLOR}"
    appcfg.py update build --oauth2
elif [ ${deploy_type} = "appscale" ]; then
    pushd build
    find . -name \*.pyc -delete
    popd
    echo Compressing files...
    tar -czf /tmp/appengine.tar.gz build
    echo -e "${LOG_COLOR}* Deploying to AppScale${NO_COLOR}"
    appscale deploy /tmp/appengine.tar.gz
    rm /tmp/appengine.tar.gz
fi

popd
