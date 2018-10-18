#!/bin/bash

# Copy ECS env vars into bash profile so they're available to SSH'd users
echo "export ENV=$ENV" >> /etc/profile
echo "export CERT_AUTHORITY_ARN=$CERT_AUTHORITY_ARN" >> /etc/profile
echo "export OIDC_RP_CLIENT_ID=$OIDC_RP_CLIENT_ID" >> /etc/profile
echo "export OIDC_PUBLIC_KEY_PEM_BASE64=$OIDC_PUBLIC_KEY_PEM_BASE64" >> /etc/profile
echo "export SERVICE=$SERVICE" >> /etc/profile
echo "export REDIS_URL=$REDIS_URL" >> /etc/profile
echo "export ENGINE_RPC_URL=$ENGINE_RPC_URL" >> /etc/profile
echo "export INTERNAL_URL=$INTERNAL_URL" >> /etc/profile
echo "export AWS_CONTAINER_CREDENTIALS_RELATIVE_URI=$AWS_CONTAINER_CREDENTIALS_RELATIVE_URI" >> /etc/profile
sed -i -e "2iexport AWS_CONTAINER_CREDENTIALS_RELATIVE_URI=$AWS_CONTAINER_CREDENTIALS_RELATIVE_URI\\" /usr/sbin/keymaker-get-public-keys
sed -i -e "2iexport AWS_CONTAINER_CREDENTIALS_RELATIVE_URI=$AWS_CONTAINER_CREDENTIALS_RELATIVE_URI\\" /usr/local/bin/keymaker-create-account-for-iam-user

echo "Loading AWS CLI virtualenv"
source /opt/aws/bin/activate

/download-certs.sh

echo "Deactivating AWS CLI virtualenv"
deactivate

exec "$@"