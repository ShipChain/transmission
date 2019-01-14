FROM python:3.6.5

LABEL maintainer="Adam Hodges <ahodges@shipchain.io>"

ENV LANG C.UTF-8
ENV PYTHONUNBUFFERED 1

RUN mkdir /build
WORKDIR /build

RUN apt-get update -y && apt-get -y install binutils libproj-dev gdal-bin rsync python3-pip

# Install poetry #
RUN curl -sSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python

# Copy Pipfiles and cache to image #
COPY pip.cache /build/pip.cache
COPY ./pyproject.toml /build/
COPY ./poetry.lock /build/

# Install dependencies from pyproject.toml (regenerate lock if necessary) #
RUN . $HOME/.poetry/env && poetry config settings.virtualenvs.create false
RUN . $HOME/.poetry/env && poetry lock && poetry install
RUN . $HOME/.poetry/env && safety check

RUN mkdir /app
WORKDIR /app

COPY ./*.sh /
RUN chmod +x /*.sh
ENTRYPOINT ["/entrypoint.sh"]
