#!/bin/bash

# Before installing 

BIN="$( cd "$( dirname "${BASH_SOURCE[0]}"  )"/.. && pwd  )"
PROJECT_DIR="$( cd $BIN/.. && pwd  )"

CACHE_STUB="compose/django/pip.cache"
CACHE_DIR="$PROJECT_DIR/$CACHE_STUB"

echo "Generating pip.cache directory"
mkdir -p $CACHE_DIR

echo "Downloading dependencies"
pushd $PROJECT_DIR
bin/ddo pip download -r compose/django/requirements.txt -d $CACHE_STUB
