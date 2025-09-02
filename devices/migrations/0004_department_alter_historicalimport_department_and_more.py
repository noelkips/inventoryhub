from django.db import migrations


def clear_device_data(apps, schema_editor):
    Import = apps.get_model('devices', 'Import')
    PendingUpdate = apps.get_model('devices', 'PendingUpdate')
    HistoricalImport = apps.get_model('devices', 'HistoricalImport')
    
    # Delete all records from Import and PendingUpdate
    Import.objects.all().delete()
    PendingUpdate.objects.all().delete()
    # Optionally clear HistoricalImport to avoid orphaned history records
    HistoricalImport.objects.all().delete()


def reverse_clear_device_data(apps, schema_editor):
    # No reverse operation since data is deleted
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('devices', '0003_clearance_created_at_alter_clearance_clearance_date_and_more'),  # Adjust to the last successful migration
    ]

    operations = [
        migrations.RunPython(
            code=clear_device_data,
            reverse_code=reverse_clear_device_data,
        ),
    ]
