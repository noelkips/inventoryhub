# devices/management/commands/rename_device_name_back_to_hardware.py
"""
Reversible command to rename 'device_name' back to 'hardware' in the database.

Use this to rollback the rename locally while testing before cloud sync.

Run with:
    python manage.py rename_device_name_back_to_hardware
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError


class Command(BaseCommand):
    help = "Renames the 'device_name' column back to 'hardware' in Import, HistoricalImport, and PendingUpdate tables."

    def handle(self, *args, **options):
        tables = [
            'devices_import',           # main table
            'devices_historicalimport', # history table (simple_history)
            'devices_pendingupdate',    # pending updates if exists
        ]

        renamed_count = 0

        with connection.cursor() as cursor:
            for table in tables:
                try:
                    # Check if 'device_name' column still exists
                    if connection.vendor == 'sqlite':
                        cursor.execute(f"""
                            SELECT 1 FROM pragma_table_info('{table}')
                            WHERE name = 'device_name'
                        """)
                    else:
                        cursor.execute(f"""
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = '{table}' AND column_name = 'device_name'
                        """)

                    if cursor.fetchone():
                        # Column exists → rename back to hardware
                        if connection.vendor == 'sqlite':
                            cursor.execute(f"""
                                ALTER TABLE {table}
                                RENAME COLUMN device_name TO hardware
                            """)
                        elif connection.vendor in ('postgresql', 'mysql'):
                            cursor.execute(f"""
                                ALTER TABLE {table}
                                RENAME COLUMN device_name TO hardware
                            """)
                        else:
                            self.stderr.write(self.style.ERROR(
                                f"Unsupported database: {connection.vendor}. Manual rename required."
                            ))
                            return

                        renamed_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f"Renamed 'device_name' → 'hardware' in table '{table}'"
                        ))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"Column 'device_name' does not exist in '{table}' — skipping."
                        ))

                except (OperationalError, ProgrammingError) as e:
                    self.stdout.write(self.style.WARNING(
                        f"Error processing '{table}': {str(e)} — likely already renamed or table missing."
                    ))

        if renamed_count == 0:
            self.stdout.write(self.style.NOTICE(
                "No columns were renamed (already in 'hardware' state or tables missing)."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nSuccessfully reverted {renamed_count} table(s) back to 'hardware'."
            ))

        self.stdout.write(self.style.SUCCESS("Rollback operation completed."))