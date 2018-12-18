FROM python:3.6.5

LABEL maintainer="Adam Hodges <ahodges@shipchain.io>"

ENV LANG C.UTF-8
ENV PYTHONUNBUFFERED 1

RUN mkdir /build
WORKDIR /build

RUN apt-get update -y && apt-get -y install binutils libproj-dev gdal-bin rsync python3-pip

# Virtualenv required for modifying Pipfile.lock #
RUN pip3 install --upgrade pip pipenv virtualenv
RUN virtualenv /opt/pipenv-venv
ENV PATH=/opt/pipenv-venv/bin:$PATH

# Copy Pipfiles and cache to image #
ENV PIPENV_CACHE_DIR=/build/pip.cache
COPY ./Pipfile* /build/
COPY pip.cache /build/pip.cache

# Install dependencies from Pipfile (regenerate lock if necessary) #
RUN . /opt/pipenv-venv/bin/activate && pipenv install --dev
# Ignoring error caused by redis-channel using outdated msgpack versions
# https://github.com/msgpack/msgpack-python/blob/master/ChangeLog.rst
# https://github.com/django/channels_redis/blob/b6ef126ff7ece67fcd22feef17eb114a124e63bb/setup.py#L35
RUN . /opt/pipenv-venv/bin/activate && pipenv check --ignore 36700

RUN mkdir /app
WORKDIR /app

COPY ./*.sh /
RUN chmod +x /*.sh
ENTRYPOINT ["/entrypoint.sh"]
