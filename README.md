<p align="center">
  <img src="https://shipchain.io/img/logo.png" alt="ShipChain"/>
</p>

[![CircleCI](https://img.shields.io/circleci/project/github/ShipChain/transmission/master.svg)](https://circleci.com/gh/ShipChain/transmission/tree/master)
[![License](http://img.shields.io/:license-apache-blue.svg)](http://www.apache.org/licenses/LICENSE-2.0.html)
[![Code style: prospector](https://img.shields.io/badge/code_style-prospector-ff69b4.svg?style=svg)](https://github.com/PyCQA/prospector)
[![Chat](https://img.shields.io/badge/gitter-ShipChain/lobby-green.svg)](https://gitter.im/ShipChain/Lobby)
[![PyUp](https://pyup.io/repos/github/ShipChain/transmission/shield.svg)](https://pyup.io/repos/github/ShipChain/transmission)


# ShipChain Transmission Project

* A service assisting in binding REST-to-Eth API calls, to simplify data access.
* Interacts with the ShipChain Engine project via RPC, implementing business logic for the ShipChain
portal and maintaining state for asynchronous transactions on the Ethereum network.

ShipChain Transmission is deployed for public consumption at [transmission.shipchain.io](https://transmission.shipchain.io) and detailed 
API documentation (OpenAPI 3.0) is available at the landing page.

## Getting Started

These instructions should provide everything needed to get a copy of Transmission up and running in your local environment.

### Prerequisites

The development environment for Transmission uses Docker to assist in the setup of local databases and supporting infrastructure.
Deployment of these containers is handled through the use of Docker Compose with the provided files in the `compose` directory.

See the official Docker documentation for installation information:

 * [Install Docker](https://docs.docker.com/engine/installation/) version > 17.09.0
 * [Install Docker Compose](https://docs.docker.com/compose/install/) version > 1.21.0
  
Transmission also relies heavily on the [ShipChain Engine](https://github.com/shipchain/engine) project for interaction 
with the Ethereum blockchain as well as wallet/vault management. Please refer to the readme in the Engine repository for
instructions on running your own Engine instance.

### Docker Compose

It is suggested to develop using Docker Compose; configuration files live in
[compose](compose/) folder, with [compose/dev.yml](compose/dev.yml) hosting several services (Redis, Postgres, Celery) 
necessary for running everything locally.

You must first run `docker network create portal` to create a local network for
other ShipChain services to communicate on (like the Profiles and Engine services).

The dev environment uses the `base` stage present in the [Dockerfile](Dockerfile); please note, this file *doesn't* use 
the docker `CP` directive to copy the project code into the container, instead the code is
mounted as a volume (so that as you save files, they update inside the container).

#### Scripts

There are several scripts in the `bin/` folder dedicated to making life simple:

* [bin/check_style](bin/check_style) will run the prospector lint tool against the repo, flagging any violations
of common Python style guides (such as PEP-8).

* [bin/docker_tests](bin/docker_tests) will run the full suite of lint checks and unit tests, as they are run
during a CircleCi build. This is useful to ensure a build is valid before pushing code.

* [bin/dc](bin/dc) is an alias for `docker-compose -f compose/dev.yml` (you could use
  e.g `compose/my_settings.yml` by setting environment variable `ROLE=my_settings`)

* [bin/dcleanup](bin/dcleanup) is quick way to "kill, remove, restart, tail logs", so if you need
to restart the `runserver` service and follow the logs you can `dcleanup runserver`

* [bin/ddo](bin/ddo) is an alias for `bin/dc run django $*`, so `ddo bash` will get you
  a shell inside a django container.

* [bin/dmg](bin/dmg) is an alias for `bin/ddo manage.py $*`, so you can quickly run
  management commands like `dmg migrate` or `dmg dbshell`

If you plan on doing a lot of development work, you might consider adding `PATH=$PATH:./bin`
to your `.bashrc` file so you can skip typing `bin/`. Ensure you first understand the security 
risks of doing so.

The scripts provided in the [bin](bin) directory allow for easier interaction with the Docker compose services and containers.
  By default, these scripts use the [dev.yml](compose/dev.yml) compose file.  This can be changed to any configuration file by setting 
  the `ROLE` environment variable.  For example if you want to use `my_settings.yml` with the scripts provided, 
  you would only need to set `ROLE=my_settings` in your environment.

### Dependencies

Transmission uses [Poetry](https://poetry.eustace.io/docs/) for dependency management. Hard dependencies are specified
in the [pyproject.toml](pyproject.toml) and then resolved into [poetry.lock](poetry.lock) by manually calling `bin/ddo poetry lock`.
The poetry.lock file enumerates every version of every dependency used in a build; this file is checked-in and versioned.

After using the `bin/dc build` command to build your local environment, `bin/ddo poetry install` needs to be run in order
to install the dependencies inside the virtualenv of the docker container. This virtualenv is cached locally in the .virtualenv
folder.

After making a change to pyproject.toml, you will need to run `bin/ddo poetry lock` to update the poetry.lock file.

### Configuration

Before you can begin using Transmission, you may need to do some configuration depending on your specific requirements.

#### Environment Variables

When utilizing the provided scripts in the [bin](bin) directory to manage the Docker containers, a file in the base folder 
named `.env` is sourced.  This allows you to inject environment variables in to the launched containers.

##### Service URLs
The URLs that Transmission uses when communicating with other services are defined in the following environment variables:

* `ENGINE_RPC_URL` - URL of the Engine RPC server
* `INTERNAL_URL` - URL of this Transmission deployment - used for Engine callbacks
* `PROFILES_URL` - URL of ShipChain Profiles, to be used for authentication. The value can also be set to `DISABLED` if 
running outside of ShipChain's infrastructure.

##### Database
 The Docker Compose files provided include a PostgreSQL container that is linked to Transmission with default connection 
 string `psql://transmission:transmission@psql:5432/transmission`.  This can be modified by setting the environment 
 variable to your preferred database:
 
* `DATABASE_URL`

##### AWS

If you intend to utilize any AWS services (such as Secrets Manager, IoT and RDS as we do in-house) you may want to include 
the following variables:
* `AWS_ACCESS_KEY_ID`
* `AWS_SECRET_ACCESS_KEY`

##### Logging

The default Python console logging level is configurable by way of environment variable. The following variable accepts any
[valid Python logging level](https://docs.python.org/3.6/library/logging.html#logging-levels), and defaults to `DEBUG`:
* `LOG_LEVEL`

##### Metrics

Transmission supports the reporting of application metrics to an InfluxDB instance. We use this internally in combination with 
Graphana to make a spiffy real-time dashboard of our application use. In order to use this, set:
* `INFLUXDB_URL` - With the format `http://{host}:{port}/{database}`

#### Pycharm Bindings (optional)
Integration with PyCharm for local development is straightforward -- you can debug the whole project
using PyCharm runners with minimal configuration.

1. Add a Remote Project Interpreter, with the following settings:

    * Type: Docker-Compose
    
    * Configuration File: compose/dev.yml
    
    * Service: runserver
    
    * Environment Variables: COMPOSE_PROJECT_NAME=transmission
    
    * Be sure to set one Path Mapping: Local Directory -> "/app/" on Remote

2. Add a Run Configuration named "runserver":

    * Type: Django Runserver
    
    * EnvFile (using EnvFile plugin): .env
    
    * Host: 0.0.0.0
    
    * Interpreter: Docker Compose Runserver Interpreter you setup above

#### Deployed Environment

While [compose/dev.yml](compose/dev.yml) is very useful for development, it's not appropriate for production use.
The service runs as a Django server (uwsgi) and is designed to be deployed behind an
nginx reverse proxy container, along with an additional Celery worker container. 
We currently use Amazon ECS (FARGATE) for deployment by way of CircleCi and AWS Lambda.

The [Dockerfile](Dockerfile) stage to build for deployment is `deploy`; `docker build --target=deploy .`
should generate the image as expected.

## Running the tests

Testing is handled through the Docker containers as well and can be invoked via the [bin/docker_tests](bin/docker_tests) script. 
This is the recommended way to run the tests. This script first runs a `prospector` lint check, followed by the unit 
tests, and finally a coverage report.

## Usage

See the public OpenAPI 3.0 documentation at [transmission.shipchain.io](https://transmission.shipchain.io) for a full enumeration of API endpoints with example requests/responses. 

### Starting Transmission
Once the dependencies are resolved, starting Transmission should be as easy as:

* `docker-compose -p transmission -f compose/dev.yml up` or
* `./bin/dc up`

By default, the [dev.yml](bin/dev.yml) compose file uses Django runserver, which is mapped to the host port 8000.

In addition, you are able to see the current Celery tasks when running locally through Flower, which is mapped to the host port 8888.

### Authentication
All endpoints require a valid JWT from OIDC Auth with the ShipChain Profiles service. The JWT shall
be provided to Transmission as a bearer token in the `Authorization` request header, in the format
`JWT {token}`. ShipChain Profiles is a full-featured OIDC provider and all JWTs will be validated using
the Profiles JWK.

Transmission's JWT authentication mechanism can be disabled by setting the `PROFILES_URL` environment variable to `DISABLED`.
This is required for the use of Transmission and Engine outside of ShipChain's infrastructure; all authentication and authorization
in this case is left up to you. 

Tracking updates from ShipChain AXLE devices are authenticated via AWS IoT, and all messages are signed
by the device itself and validated using the device's AWS IoT certificate. If `ENVIRONMENT` is set to `LOCAL`,
all AWS IoT validation is disabled, and devices should post their raw payloads directly to the endpoint.

### Asynchronous Requests
Transmission interacts with ShipChain Engine asynchronously; any long-running Engine RPC calls are passed a callback
to a Transmission endpoint. When Transmission receives an update about a job, the relevant listeners
are notified, updating the data model and pushing notifications to all relevant channels.

### Postman
There is a Postman collection available for import at [tests/postman.collection.Transmission.json](tests/postman.collection.Transmission.json).
This can be imported into Postman to provide a collection of all available Transmission endpoints for ease of testing. 
Please note that this collection is designed to be used with ShipChain Profiles - if you are using it for your own internal
testing, you will need to disable authentication on all of the requests in the collection.

## Built With

* [Django](https://www.djangoproject.com/) - Python MVC web framework
* [Django Rest Framework](http://www.django-rest-framework.org/) - REST API toolkit
* [Celery](http://www.celeryproject.org/) - Distributed task queue

<!--## Contributing

Please read [CONTRIBUTING.md](https://gist.github.com/PurpleBooth/b24679402957c63ec426) for details on our code of 
conduct, and the process for submitting pull requests to us.
-->

## Versioning

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the 
[tags on this repository](https://github.com/shipchain/transmission/tags).

## Authors

* **Adam Hodges** - [ajhodges](https://github.com/ajhodges)
* **Clovis Djiometsa** - [clovisdj](https://github.com/ClovisDj)
* **James Neyer** - [jamesfneyer](https://github.com/jamesfneyer)
* **Lucas Clay** - [mlclay](https://github.com/mlclay)
* **Leeward Bound** - [leewardbound](https://github.com/leewardbound)
* **Kevin Duck** - [kevingduck](https://github.com/kevingduck)

See also the list of [contributors](https://github.com/ShipChain/transmission/contributors) who participated in this project.

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details
