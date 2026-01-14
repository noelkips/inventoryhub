import subprocess
import os
import tempfile
import sys
from django.core.management.base import BaseCommand
from devices.utils import send_custom_email
from datetime import datetime


class Command(BaseCommand):
    help = "Dumps database and emails it as JSON backup"

    def handle(self, *args, **options):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"inventoryhub_backup_{timestamp}.json"

            # Create temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_file:
                filepath = temp_file.name

            # Build dump command (force UTF-8)
            dump_command = [
                sys.executable,
                "-X", "utf8",          # 🔴 CRITICAL: forces UTF-8 on Windows
                "manage.py",
                "dumpdata",
                "--exclude", "auth.permission",
                "--exclude", "contenttypes",
                "--natural-foreign",
                "--natural-primary",
                "--indent", "2"
            ]

            # Run dump directly into file
            with open(filepath, "w", encoding="utf-8") as f:
                subprocess.run(dump_command, stdout=f, stderr=subprocess.PIPE, check=True)

            # Read file
            with open(filepath, "rb") as f:
                file_bytes = f.read()

            subject = "Daily InventoryHub Database Backup"
            message = (
                "Hello,\n\n"
                "Attached is the daily automated backup of the InventoryHub database.\n\n"
                "Regards,\nInventoryHub System"
            )

            recipients = [
                "itinventory@mohiafrica.org",
                "noel.langat@mohiafrica.org",
                "santana.macharia@mohiafrica.org"
            ]

            send_custom_email(
                subject=subject,
                message=message,
                recipient_list=recipients,
                attachment=(filename, file_bytes, "application/json")
            )

            os.remove(filepath)

            self.stdout.write(self.style.SUCCESS("Database backup dumped and emailed successfully."))

        except subprocess.CalledProcessError as e:
            self.stderr.write(self.style.ERROR(f"Dumpdata failed: {e.stderr.decode(errors='ignore')}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Backup failed: {e}"))
