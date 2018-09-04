#!/bin/bash
set -e
BIN="$( cd "$( dirname "${BASH_SOURCE[0]}"  )"/.. && pwd  )"
PROJECT_DIR="$( cd $BIN/.. && pwd  )"

source $BIN/dev-tools/utils.sh

pushd $PROJECT_DIR

color_header "Creating portal network"
docker network create portal || color_header "Already exists!" $COLOR_YELLOW

color_header "Building containers"
bin/dc build

color_header "Starting services"
bin/dc up -d

color_header "Caching build files"
bin/dev-tools/cache_pip_wheels.sh

color_header "Five second pause to warm up" $COLOR_YELLOW
sleep 5

color_header "Running migrations"
bin/dmg migrate

color_header "Restarting dev server and following logs..." $COLOR_GREEN
bin/dcleanup runserver
