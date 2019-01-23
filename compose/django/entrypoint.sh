#!/bin/bash

if [[ ! -f $VIRTUAL_ENV/bin/python ]];
then
    echo "Creating virtualenv"
    virtualenv $VIRTUAL_ENV
fi

if [[ "$ENV" = "PROD" ]] || [[ "$ENV" = "DEMO" ]] || [[ "$ENV" = "STAGE" ]] || [[ "$ENV" = "DEV" ]];
then
    echo "Not running in a docker-compose environment, skipping wait-for-it"

    echo "Loading AWS CLI virtualenv"
    source /opt/aws/bin/activate

    /download-certs.sh

    echo "Deactivating AWS CLI virtualenv"
    deactivate
elif [[ -z "$IS_DDO" ]];
then
    echo "Waiting for dependencies to come up in the stack"
    /wait-for-it.sh ${REDIS_NAME:-redis_db}:6379
    /wait-for-it.sh ${PSQL_NAME:-psql}:5432
    /wait-for-it.sh ${MINIO_NAME:-minio}:9000

    python manage.py migrate
fi

exec "$@"