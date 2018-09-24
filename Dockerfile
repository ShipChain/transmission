FROM python:3.6.5

LABEL maintainer="Adam Hodges <ahodges@shipchain.io>"

ENV LANG C.UTF-8
ENV PYTHONUNBUFFERED 1

RUN mkdir /build
WORKDIR /build

# SUPPORT SSH FOR IAM USERS #
RUN apt-get update && apt-get -y install openssh-server
RUN mkdir /var/run/sshd /etc/cron.d
RUN pip install keymaker
RUN keymaker install

# Configure public key SSH
RUN echo "AllowAgentForwarding yes" >> /etc/ssh/sshd_config
RUN echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
# ------------------------- #

RUN apt-get update -y && apt-get -y install binutils libproj-dev gdal-bin rsync

COPY ./compose/django/requirements.txt /build/
COPY ./compose/django/pip.cache /build/pip.cache
RUN pip install -r /build/requirements.txt --cache-dir=/build/pip.cache

RUN mkdir /app
WORKDIR /app

COPY ./compose/django/*.sh /
RUN chmod +x /*.sh
ENTRYPOINT ["/entrypoint.sh"]

ADD . /app/

# Generate static assets
RUN python manage.py collectstatic -c --noinput
