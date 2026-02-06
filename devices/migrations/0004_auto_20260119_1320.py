# devices/migrations/0004_backfill_data_safe.py
from django.db import migrations, connection, transaction

def create_missing_tables_and_backfill(apps, schema_editor):
    Employee = apps.get_model('devices', 'Employee')
    Import = apps.get_model('devices', 'Import')
    DeviceAgreement = apps.get_model('devices', 'DeviceAgreement')

    cursor = connection.cursor()

    # ------------------------
    # Helper to check table
    # ------------------------
    def table_exists(table_name):
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        return cursor.fetchone() is not None

    # ------------------------
    # Helper to check column
    # ------------------------
    def column_exists(table_name, column_name):
        with connection.cursor() as cursor:
            for col in connection.introspection.get_table_description(cursor, table_name):
                if col.name == column_name:
                    return True
        return False

    # ------------------------
    # Ensure Import table has required columns
    # ------------------------
    columns_to_add = [
        ('device_name', "TEXT"),
        ('assignee_cache', "TEXT"),
        ('uaf_signed', "BOOLEAN")
    ]
    for col, col_type in columns_to_add:
        if not column_exists('devices_import', col):
            cursor.execute(f"ALTER TABLE devices_import ADD COLUMN {col} {col_type}")

    # ------------------------
    # Backfill Employee and DeviceAgreement safely
    # ------------------------
    with transaction.atomic():
        for device in Import.objects.all():
            # Attempt to get Employee by email first (preferred)
            employee = None
            if device.assignee_email_address:
                employee = Employee.objects.filter(email=device.assignee_email_address).first()
            
            # If not found, fallback to first+last name
            if not employee and (device.assignee_first_name or device.assignee_last_name):
                employee = Employee.objects.filter(
                    first_name=device.assignee_first_name or "",
                    last_name=device.assignee_last_name or ""
                ).first()
            
            # If still not found, create a new Employee
            if not employee and (device.assignee_first_name or device.assignee_last_name):
                employee = Employee.objects.create(
                    first_name=device.assignee_first_name or "",
                    last_name=device.assignee_last_name or "",
                    email=device.assignee_email_address or None
                )

            # Link Employee to device
            if employee:
                device.assignee = employee
                device.assignee_cache = str(employee)
                device.save()

            # Ensure DeviceAgreement exists
            if employee:
                DeviceAgreement.objects.get_or_create(
                    device=device,
                    employee=employee
                )

class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0003_rename_hardware_historicalimport_device_name_and_more'),
    ]

    operations = [
        migrations.RunPython(create_missing_tables_and_backfill),
    ]
