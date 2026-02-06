# devices/management/commands/rename_hardware_to_device_name.py

from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = "Rename 'hardware' → 'device_name' in main and historical tables safely"

    TABLES = [
        "devices_import",
        "devices_pendingupdate",
        "devices_historicalimport",  # <-- historical table
    ]

    OLD_COLUMN = "hardware"
    NEW_COLUMN = "device_name"

    def handle(self, *args, **kwargs):
        vendor = connection.vendor
        for table in self.TABLES:
            # Check if the old column exists
            if vendor == "sqlite":
                connection.cursor().execute(
                    f"SELECT 1 FROM pragma_table_info('{table}') WHERE name='{self.OLD_COLUMN}'"
                )
                exists = connection.cursor().fetchone() is not None
            elif vendor in ("postgresql", "mysql"):
                connection.cursor().execute(
                    f"""
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name='{table}' AND column_name='{self.OLD_COLUMN}'
                    """
                )
                exists = connection.cursor().fetchone() is not None
            else:
                self.stdout.write(self.style.ERROR(f"Unsupported DB vendor: {vendor}"))
                return

            if exists:
                self.stdout.write(self.style.SUCCESS(f"Renaming column in {table}..."))
                if vendor == "sqlite":
                    # SQLite supports simple RENAME COLUMN
                    connection.cursor().execute(
                        f"ALTER TABLE {table} RENAME COLUMN {self.OLD_COLUMN} TO {self.NEW_COLUMN}"
                    )
                else:
                    # PostgreSQL / MySQL
                    connection.cursor().execute(
                        f"ALTER TABLE {table} RENAME COLUMN {self.OLD_COLUMN} TO {self.NEW_COLUMN}"
                    )
                self.stdout.write(self.style.SUCCESS(f"✅ {table}: {self.OLD_COLUMN} → {self.NEW_COLUMN}"))
            else:
                self.stdout.write(self.style.WARNING(f"Skipped {table}: column '{self.OLD_COLUMN}' does not exist"))

        self.stdout.write(self.style.SUCCESS("\nAll tables processed."))
