import csv
from django.core.management.base import BaseCommand
from devices.models import Import

class Command(BaseCommand):
    help = 'Export all Import model data to a CSV file'

    def handle(self, *args, **kwargs):
        # Define the output CSV file path
        output_file = 'import_data_export.csv'

        # Get all Import records
        imports = Import.objects.all()

        # Define CSV headers based on Import model fields
        headers = [
            'id',
            'file',
            'centre',
            'department',
            'hardware',
            'system_model',
            'processor',
            'ram_gb',
            'hdd_gb',
            'serial_number',
            'assignee_first_name',
            'assignee_last_name',
            'assignee_email_address',
            'device_condition',
            'status',
            'date'
        ]

        # Write to CSV file with UTF-8 encoding
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            # Write header row
            writer.writerow(headers)

            # Write data rows
            for import_record in imports:
                writer.writerow([
                    import_record.id,
                    str(import_record.file) if import_record.file else '',
                    import_record.centre or '',  # centre is a CharField, export as is
                    import_record.department or '',
                    import_record.hardware or '',
                    import_record.system_model or '',
                    import_record.processor or '',
                    import_record.ram_gb or '',
                    import_record.hdd_gb or '',
                    import_record.serial_number or '',
                    import_record.assignee_first_name or '',
                    import_record.assignee_last_name or '',
                    import_record.assignee_email_address or '',
                    import_record.device_condition or '',
                    import_record.status or '',
                    import_record.date.isoformat() if import_record.date else ''
                ])

        self.stdout.write(self.style.SUCCESS(f'Successfully exported {imports.count()} records to {output_file}'))