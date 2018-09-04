# Generated by Django 2.0.7 on 2018-07-27 18:54

import apps.utils
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('shipments', '0003_auto_20180716_1848'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoadShipment',
            fields=[
                ('id', models.CharField(default=apps.utils.random_id, max_length=36, primary_key=True, serialize=False)),
                ('shipment_id', models.IntegerField(db_index=True)),
                ('shipment_amount', models.IntegerField()),
                ('paid_amount', models.IntegerField(default=0)),
                ('paid_tokens', models.DecimalField(decimal_places=18, max_digits=40)),
                ('shipper', models.CharField(max_length=42)),
                ('carrier', models.CharField(max_length=42)),
                ('moderator', models.CharField(max_length=42, null=True)),
                ('contract_funded', models.BooleanField()),
                ('shipment_created', models.BooleanField()),
                ('valid_until', models.IntegerField()),
                ('start_block', models.IntegerField()),
                ('end_block', models.IntegerField(null=True)),
                ('escrow_funded', models.BooleanField()),
                ('shipment_committed_by_carrier', models.BooleanField()),
                ('commitment_confirmed_date', models.IntegerField()),
                ('shipment_completed_by_carrier', models.BooleanField()),
                ('shipment_accepted_by_shipper', models.BooleanField()),
                ('shipment_canceled_by_shipper', models.BooleanField()),
                ('escrow_paid', models.BooleanField()),
            ],
        ),
        migrations.AlterModelOptions(
            name='location',
            options={},
        ),
        migrations.AddField(
            model_name='shipment',
            name='carrier_wallet_id',
            field=models.CharField(default=1234, max_length=36),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='shipment',
            name='shipper_wallet_id',
            field=models.CharField(default=1234, max_length=36),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='shipment',
            name='storage_credentials_id',
            field=models.CharField(default=1234, max_length=36),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='shipment',
            name='vault_id',
            field=models.CharField(max_length=36, null=True),
        ),
        migrations.AddField(
            model_name='shipment',
            name='load_data',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='shipments.LoadShipment'),
        ),
    ]
