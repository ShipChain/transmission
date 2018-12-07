# Generated by Django 2.1.4 on 2018-12-07 19:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='document',
            old_name='uploaded_at',
            new_name='created_at',
        ),
        migrations.RemoveField(
            model_name='document',
            name='size',
        ),
        migrations.AddField(
            model_name='document',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
