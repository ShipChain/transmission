FROM python:3.6.5

LABEL maintainer="Adam Hodges <ahodges@shipchain.io>"

ENV LANG C.UTF-8
ENV PYTHONUNBUFFERED 1

RUN mkdir /build
WORKDIR /build

RUN apt-get update -y && apt-get -y install binutils libproj-dev gdal-bin rsync python3-pip

RUN pip3 install --upgrade pip pipenv

COPY ./Pipfile* /build/
COPY pip.cache /build/pip.cache
ENV PIPENV_CACHE_DIR=/build/pip.cache
RUN pipenv install --system --dev

RUN mkdir /app
WORKDIR /app

COPY ./*.sh /
RUN chmod +x /*.sh
ENTRYPOINT ["/entrypoint.sh"]
