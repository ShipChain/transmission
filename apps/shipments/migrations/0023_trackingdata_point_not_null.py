# Generated by Django 2.0.10 on 2019-01-21 21:35

import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('shipments', '0022_shipment_route_jsonfield_squashed_0024_trackingdata_point_data_migration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trackingdata',
            name='point',
            field=django.contrib.gis.db.models.fields.GeometryField(srid=4326),
        ),
    ]
