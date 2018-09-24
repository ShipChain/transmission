FROM python:3.6.5

LABEL maintainer="Adam Hodges <ahodges@shipchain.io>"

ENV LANG C.UTF-8
ENV PYTHONUNBUFFERED 1

RUN mkdir /build
WORKDIR /build

RUN apt-get update -y && apt-get -y install binutils libproj-dev gdal-bin rsync

COPY ./requirements.txt /build/
COPY pip.cache /build/pip.cache
RUN pip install -r /build/requirements.txt --cache-dir=/build/pip.cache

RUN mkdir /app
WORKDIR /app

COPY ./*.sh /
RUN chmod +x /*.sh
ENTRYPOINT ["/entrypoint.sh"]
