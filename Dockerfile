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
RUN pip3 install --upgrade pip
RUN curl -sSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python

# Use pip caching
COPY compose/django/pip.cache /build/pip.cache
COPY compose/django/pyproject.toml /build/
COPY compose/django/poetry.lock /build/

# Install dependencies from pyproject.toml (regenerate lock if necessary) #
RUN . $HOME/.poetry/env && poetry config settings.virtualenvs.create false
RUN . $HOME/.poetry/env && poetry install
RUN . $HOME/.poetry/env && safety check

RUN mkdir /app
WORKDIR /app

COPY ./compose/django/*.sh /
RUN chmod +x /*.sh
ENTRYPOINT ["/entrypoint.sh"]

ADD . /app/

# Generate static assets
RUN python manage.py collectstatic -c --noinput
