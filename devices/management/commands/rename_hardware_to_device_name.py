# devices/management/commands/rename_hardware_to_device_name.py
"""
One-time command to rename 'hardware' column to 'device_name' across relevant tables.

Run with:
    python manage.py rename_hardware_to_device_name

This is safe to run multiple times — it checks if the column exists first.
"""

from django.core.management.base import BaseCommand
from django.db import connection, migrations
from django.db.utils import OperationalError, ProgrammingError


class Command(BaseCommand):
    help = "Renames the 'hardware' column to 'device_name' in Import, HistoricalImport, and PendingUpdate tables."

    def handle(self, *args, **options):
        tables = [
            'devices_import',           # main table
            'devices_historicalimport', # history table (simple_history)
            'devices_pendingupdate',    # pending updates if you have that model
        ]

        with connection.cursor() as cursor:
            for table in tables:
                try:
                    # Check if 'hardware' column still exists
                    cursor.execute(f"""
                        SELECT 1 FROM pragma_table_info('{table}')
                        WHERE name = 'hardware'
                    """) if connection.vendor == 'sqlite' else \
                    cursor.execute(f"""
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = '{table}' AND column_name = 'hardware'
                    """)

                    if cursor.fetchone():
                        # Column exists → rename it
                        if connection.vendor == 'sqlite':
                            cursor.execute(f"""
                                ALTER TABLE {table}
                                RENAME COLUMN hardware TO device_name
                            """)
                        elif connection.vendor in ('postgresql', 'mysql'):
                            cursor.execute(f"""
                                ALTER TABLE {table}
                                RENAME COLUMN hardware TO device_name
                            """)
                        else:
                            self.stderr.write(self.style.ERROR(
                                f"Unsupported database: {connection.vendor}. Manual rename required."
                            ))
                            return

                        self.stdout.write(self.style.SUCCESS(
                            f"Successfully renamed 'hardware' → 'device_name' in table '{table}'"
                        ))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"Column 'hardware' does not exist in '{table}' — skipping."
                        ))

                except (OperationalError, ProgrammingError) as e:
                    self.stdout.write(self.style.WARNING(
                        f"Error processing '{table}': {str(e)} — likely already renamed or table missing."
                    ))

        self.stdout.write(self.style.SUCCESS("\nRename operation completed."))