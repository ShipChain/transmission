# Generated by Django 2.0.7 on 2018-08-15 15:26

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('eth', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='contract_receipt',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='eth.ContractReceipt'),
        ),
    ]
