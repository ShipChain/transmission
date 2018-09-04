#!/bin/sh

if [ "$ENV" = "PROD" ] || [ "$ENV" = "STAGE" ] || [ "$ENV" = "DEV" ];
then
    echo "Not running in a docker-compose environment, skipping wait-for-it"
else
    echo "Waiting for dependencies to come up in the stack"
    /wait-for-it.sh ${REDIS_NAME:-redis_db}:6379
    /wait-for-it.sh ${PSQL_NAME:-psql}:5432
fi

python manage.py migrate
exec "$@"