FROM python:3.6.5

LABEL maintainer="Adam Hodges <ahodges@shipchain.io>"

ENV LANG C.UTF-8
ENV PYTHONUNBUFFERED 1

RUN mkdir /build
WORKDIR /build

ADD ./requirements.txt /build/
ADD ./pip.cache/ /build/

RUN apt-get update -y && apt-get -y install binutils libproj-dev gdal-bin

RUN pip install -r /build/requirements.txt --find-links /build/

RUN mkdir /app
WORKDIR /app

COPY ./*.sh /
RUN chmod +x /*.sh
ENTRYPOINT ["/entrypoint.sh"]
