# Generated by Django 3.0.8 on 2020-08-24 13:50

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('shipments', '0020_accessrequest'),
    ]

    operations = [
        migrations.RenameField(
            model_name='historicalshipment',
            old_name='aftership_tracking',
            new_name='quickadd_tracking',
        ),
        migrations.RenameField(
            model_name='shipment',
            old_name='aftership_tracking',
            new_name='quickadd_tracking',
        ),
    ]