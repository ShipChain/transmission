FROM python:3.6.5

LABEL maintainer="Adam Hodges <ahodges@shipchain.io>"

ENV LANG C.UTF-8
ENV PYTHONUNBUFFERED 1

RUN mkdir /build
WORKDIR /build

# SUPPORT SSH FOR IAM USERS #
RUN apt-get update && apt-get -y install openssh-server python3-pip
RUN mkdir /var/run/sshd /etc/cron.d
RUN pip3 install keymaker
RUN keymaker install

# Configure public key SSH
RUN echo "AllowAgentForwarding yes" >> /etc/ssh/sshd_config
RUN echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
# ------------------------- #

RUN apt-get update -y && apt-get -y install binutils libproj-dev gdal-bin rsync jq

# Virtualenv for awscli #
RUN pip3 install virtualenv
RUN virtualenv /opt/aws
RUN . /opt/aws/bin/activate && pip3 install --upgrade awscli

# Dependencies installation from Pipfile.lock
RUN pip3 install --upgrade pip pipenv

# Use pip caching
ENV PIPENV_CACHE_DIR=/build/pip.cache
COPY compose/django/Pipfile* /build/
COPY compose/django/pip.cache /build/pip.cache

RUN pipenv install --dev --deploy --system
# Ignoring error caused by redis-channel using outdated msgpack versions
# https://github.com/msgpack/msgpack-python/blob/master/ChangeLog.rst
# https://github.com/django/channels_redis/blob/b6ef126ff7ece67fcd22feef17eb114a124e63bb/setup.py#L35
RUN pipenv check --system  --ignore 36700

RUN mkdir /app
WORKDIR /app

COPY ./compose/django/*.sh /
RUN chmod +x /*.sh
ENTRYPOINT ["/entrypoint.sh"]

ADD . /app/

# Generate static assets
RUN python manage.py collectstatic -c --noinput
