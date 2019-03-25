# Generated by Django 2.1.7 on 2019-03-21 20:20

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


def enforce_unique_locations(apps, schema_editor):
    existing_locations_seen = set()
    Shipment = apps.get_model('shipments', 'Shipment')
    for shipment in Shipment.objects.all():
        if shipment.ship_from_location_id:
            if shipment.ship_from_location_id in existing_locations_seen:
                shipment.ship_from_location.pk = None
                shipment.ship_from_location.id = None
                shipment.ship_from_location.save()
                Shipment.objects.filter(id=shipment.id).update(ship_from_location_id=shipment.ship_from_location.id)
            existing_locations_seen.add(shipment.ship_from_location.id)

        if shipment.ship_to_location_id:
            if shipment.ship_to_location_id in existing_locations_seen:
                shipment.ship_to_location.pk = None
                shipment.ship_to_location.id = None
                shipment.ship_to_location.save()
                Shipment.objects.filter(id=shipment.id).update(ship_to_location_id=shipment.ship_to_location.id)
            existing_locations_seen.add(shipment.ship_to_location.id)

        if shipment.final_destination_location_id:
            if shipment.final_destination_location_id in existing_locations_seen:
                shipment.final_destination_location.pk = None
                shipment.final_destination_location.id = None
                shipment.final_destination_location.save()
                Shipment.objects.filter(id=shipment.id).update(final_destination_location_id=shipment.final_destination_location.id)
            existing_locations_seen.add(shipment.final_destination_location.id)

        if shipment.bill_to_location_id:
            if shipment.bill_to_location_id in existing_locations_seen:
                shipment.bill_to_location.pk = None
                shipment.bill_to_location.id = None
                shipment.bill_to_location.save()
                Shipment.objects.filter(id=shipment.id).update(bill_to_location_id=shipment.bill_to_location.id)
            existing_locations_seen.add(shipment.bill_to_location.id)


class Migration(migrations.Migration):

    dependencies = [
        ('shipments', '0032_location_country_data_migration'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='location',
            name='owner_id',
        ),
        migrations.RunPython(enforce_unique_locations),
        migrations.AlterField(
            model_name='location',
            name='country',
            field=models.CharField(blank=True, max_length=2, null=True, validators=[django.core.validators.RegexValidator(message='Invalid ISO 3166-1 alpha-2 country code.', regex='^A[^ABCHJKNPVY]|B[^CKPUX]|C[^BEJPQST]|D[EJKMOZ]|E[CEGHRST]|F[IJKMOR]|G[^CJKOVXZ]|H[KMNRTU]|I[DEL-OQ-T]|J[EMOP]|K[EGHIMNPRWYZ]|L[ABCIKR-VY]|M[^BIJ]|N[ACEFGILOPRUZ]|OM|P[AE-HK-NRSTWY]|QA|R[EOSUW]|S[^FPQUW]|T[^ABEIPQSUXY]|U[AGMSYZ]|V[ACEGINU]|WF|WS|YE|YT|Z[AMW]')]),
        ),
        migrations.AlterField(
            model_name='shipment',
            name='bill_to_location',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='shipment_bill', to='shipments.Location'),
        ),
        migrations.AlterField(
            model_name='shipment',
            name='final_destination_location',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='shipment_dest', to='shipments.Location'),
        ),
        migrations.AlterField(
            model_name='shipment',
            name='ship_from_location',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='shipment_from', to='shipments.Location'),
        ),
        migrations.AlterField(
            model_name='shipment',
            name='ship_to_location',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='shipment_to', to='shipments.Location'),
        ),
    ]