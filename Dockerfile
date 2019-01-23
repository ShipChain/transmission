FROM python:3.6.8-slim AS base

LABEL maintainer="Adam Hodges <ahodges@shipchain.io>"

ENV LANG C.UTF-8
ENV PYTHONUNBUFFERED 1

# Essential packages for our app environment
RUN apt-get update && \
    apt-get -y --no-install-recommends install binutils libproj-dev gdal-bin curl && \
    curl -sSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python && \
    apt-get remove -y curl && \
    apt-get autoremove --purge -y && \
    rm -rf /var/lib/apt/lists/*

# Install and configure virtualenv
RUN pip install virtualenv
ENV VIRTUAL_ENV=/app/.virtualenv
ENV PATH=$VIRTUAL_ENV/bin:/root/.poetry/bin:$PATH

# Initialize app dir and entrypoint scripts
RUN mkdir /app
WORKDIR /app
COPY ./compose/django/*.sh /
RUN chmod +x /*.sh
ENTRYPOINT ["/entrypoint.sh"]

## Image only used for production building ##
FROM base AS build

# Essential packages for building python packages
RUN apt-get update && \
    apt-get -y --no-install-recommends install build-essential git  && \
    apt-get autoremove --purge -y && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY . /app/
RUN \[ -d $VIRTUAL_ENV \] || virtualenv $VIRTUAL_ENV
RUN . $VIRTUAL_ENV/bin/activate && poetry install --no-dev

# Generate static assets
RUN python manage.py collectstatic -c --noinput

## Image to be deployed to ECS with additional utils and no build tools ##
FROM base AS deploy

# Install openssh for ECS management container
RUN apt-get update && \
    apt-get -y --no-install-recommends install jq openssh-server  && \
    apt-get autoremove --purge -y && \
    rm -rf /var/lib/apt/lists/*

# Keymaker for SSH auth via IAM
RUN mkdir /var/run/sshd /etc/cron.d
RUN pip install keymaker
RUN keymaker install

# Configure public key SSH
RUN echo "AllowAgentForwarding yes" >> /etc/ssh/sshd_config
RUN echo "PasswordAuthentication no" >> /etc/ssh/sshd_config

# Create virtualenv for using awscli in entrypoint scripts
RUN virtualenv /opt/aws
RUN . /opt/aws/bin/activate && pip install --upgrade awscli

# Copy built virtualenv without having to install build-essentials, etc
COPY --from=build /app /app

## Image with dev-dependencies ##
FROM build AS test

RUN . $VIRTUAL_ENV/bin/activate && poetry install