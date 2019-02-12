# pylint:disable=invalid-name
import logging
import datetime

from django.conf import settings

from celery import shared_task
from influxdb_metrics.loader import log_metric

from apps.rpc_client import RPCError
from .rpc import DocumentRPCClient
from .models import Document, UploadStatus

LOG = logging.getLogger('transmission')


@shared_task(bind=True, autoretry_for=(RPCError,),
             retry_backoff=3, retry_backoff_max=60, max_retries=10)
def get_document_from_vault(self, document_id):

    doc = Document.objects.filter(id=document_id).first()

    LOG.info(f'Repopulating s3 with document: {doc}, from vault: {doc.shipment.vault_id}')
    log_metric('transmission.info', tags={'method': 'documents.tasks.get_document_from_vault',
                                          'module': __name__})

    today = datetime.datetime.now().date()
    delta_days = settings.S3_DOCUMENT_EXPIRATION
    from_vault_date = doc.accessed_from_vault_on

    fetch_from_vault = (from_vault_date and from_vault_date + datetime.timedelta(days=delta_days) < today) or \
                       (doc.created_at.date() + datetime.timedelta(days=delta_days) < today)

    if doc.upload_status == UploadStatus.COMPLETE and fetch_from_vault:

        storage_credentials_id, wallet_id, vault_id, filename = doc.s3_key.split('/', 3)

        DocumentRPCClient().put_document_to_s3(settings.S3_BUCKET,
                                               doc.s3_key,
                                               wallet_id,
                                               storage_credentials_id,
                                               vault_id, filename)

        doc.accessed_from_vault_on = today
        doc.save()
