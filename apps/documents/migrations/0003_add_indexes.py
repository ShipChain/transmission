# Generated by Django 2.2.12 on 2020-04-10 18:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0002_historical_document'),
    ]

    operations = [
        migrations.AlterField(
            model_name='historicaldocument',
            name='history_date',
            field=models.DateTimeField(db_index=True),
        ),
    ]