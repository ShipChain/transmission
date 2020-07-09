from moto import mock_s3
from shipchain_common.test_utils import AssertionHelper

from apps.documents.models import Document, DocumentType, FileType
from pytest import fixture
from django.conf import settings

from apps.utils import UploadStatus


def build_entity_ref(document, shipment_relation):
    return AssertionHelper.EntityRef(
        resource='Document',
        pk=document.id,
        attributes={
            'upload_status': document.upload_status.name,
            'file_type': document.file_type.name,
            'document_type': document.document_type.name,
            'description': document.description,
            'owner_id': document.owner_id
        },
        relationships=[{
            'shipment': shipment_relation
        }]
    )


@fixture
def mock_s3_buckets():
    mock_s3().start()
    s3_resource = settings.S3_RESOURCE
    s3_resource.create_bucket(Bucket=settings.DOCUMENT_MANAGEMENT_BUCKET)
    yield s3_resource
    for bucket in s3_resource.buckets.all():
        for key in bucket.objects.all():
            key.delete()
        bucket.delete()


@fixture
def document_shipment_alice(shipment_alice):
    return Document.objects.create(
        owner_id=shipment_alice.owner_id,
        document_type=DocumentType.BOL,
        file_type=FileType.PDF,
        shipment=shipment_alice,
        upload_status=UploadStatus.PENDING
    )


@fixture
def document_shipment_alice_two(shipment_alice):
    return Document.objects.create(
        owner_id=shipment_alice.owner_id,
        document_type=DocumentType.AIR_WAYBILL,
        file_type=FileType.JPEG,
        shipment=shipment_alice,
        upload_status=UploadStatus.FAILED
    )


@fixture
def document_shipment_two_alice(shipment_alice_two):
    return Document.objects.create(
        owner_id=shipment_alice_two.owner_id,
        document_type=DocumentType.BOL,
        file_type=FileType.PDF,
        shipment=shipment_alice_two,
        upload_status=UploadStatus.PENDING
    )


@fixture
def entity_ref_document_shipment_alice(document_shipment_alice, entity_ref_shipment_alice):
    return build_entity_ref(document_shipment_alice, entity_ref_shipment_alice)


@fixture
def entity_ref_document_shipment_alice_two(document_shipment_alice_two, entity_ref_shipment_alice):
    return build_entity_ref(document_shipment_alice_two, entity_ref_shipment_alice)


@fixture
def entity_ref_document_shipment_two_alice(document_shipment_two_alice, entity_ref_shipment_alice_two):
    return build_entity_ref(document_shipment_two_alice, entity_ref_shipment_alice_two)
