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

# Dependencies installation
RUN pip3 install --upgrade pip pipenv
COPY compose/django/Pipfile /build/Pipfile
RUN pipenv install --skip-lock --system

RUN mkdir /app
WORKDIR /app

COPY ./compose/django/*.sh /
RUN chmod +x /*.sh
ENTRYPOINT ["/entrypoint.sh"]

ADD . /app/

# Generate static assets
RUN python manage.py collectstatic -c --noinput
