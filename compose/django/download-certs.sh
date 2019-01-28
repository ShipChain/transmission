#!/usr/bin/env bash

echo "Downloading certificates from ACM"

SUBDOMAIN=$APP.${ENV,,}-internal

echo "Looking for existing certificate in ACM"
CERT_ARN=$(aws acm list-certificates | jq -r "[.CertificateSummaryList[] | select(.DomainName == \"$SUBDOMAIN\")][0].CertificateArn")

# Create private certificate in AWS ACM
if [ $CERT_ARN = "null" ];
then
  echo "Creating new certificate"
  CERT_ARN=$(aws --region us-east-1 acm request-certificate \
  --domain-name $SUBDOMAIN \
  --idempotency-token $APP$ENV \
  --options CertificateTransparencyLoggingPreference=DISABLED \
  --certificate-authority-arn $CERT_AUTHORITY_ARN | jq -r '.CertificateArn')

  echo "Waiting for certificate to be ready"
  STATUS=$(aws acm describe-certificate --certificate-arn $CERT_ARN | jq -r '.Certificate.Status')
  while [ $STATUS != "ISSUED" ] && [ $STATUS != "FAILED" ]
  do
    sleep 2
    STATUS=$(aws acm describe-certificate --certificate-arn $CERT_ARN | jq -r '.Certificate.Status')
  done

  echo "Tagging certificate"
  aws acm add-tags-to-certificate --certificate-arn $CERT_ARN --tags Key=Name,Value=$SUBDOMAIN
fi

# Export certificate as JSON
echo "Exporting certificate"
CERT_PASS=$(openssl rand -base64 12)
CERT_JSON=$(aws --region us-east-1 acm export-certificate --certificate-arn $CERT_ARN --passphrase $CERT_PASS)
CA_CERT_JSON=$(aws --region us-east-1 acm-pca get-certificate-authority-certificate --certificate-authority-arn $CERT_AUTHORITY_ARN)

# Copy certificate to nodejs
echo "Copying certificate to app"
echo $CERT_JSON | jq -r '.Certificate' >> /app/client-cert.crt
echo $CERT_JSON | jq -r '.CertificateChain' >> /app/client-cert.crt
echo $CERT_JSON | jq -r '.PrivateKey' > /app/client-cert.encrypted.key
echo $CA_CERT_JSON | jq -r '.Certificate' >> /app/ca-bundle.crt
echo $CA_CERT_JSON | jq -r '.CertificateChain' >> /app/ca-bundle.crt

# Decrypt key
openssl rsa -passin pass:$CERT_PASS -in /app/client-cert.encrypted.key -out /app/client-cert.key
chmod 644 /app/client-cert.key  # Change permission level so Django can read it