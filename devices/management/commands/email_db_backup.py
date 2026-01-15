import subprocess
import os
import tempfile
import sys
from django.core.management.base import BaseCommand
from devices.utils import send_custom_email
from datetime import datetime
from cryptography.fernet import Fernet
import base64
import hashlib
from itinventory.settings import BACKUP_PASSWORD

class Command(BaseCommand):
    help = "Dumps database, encrypts it with password, and emails it"

    # 🔴 CHANGE THIS PASSWORD
    BACKUP_PASSWORD = BACKUP_PASSWORD

    def derive_key(self, password: str) -> bytes:
        """
        Derive a Fernet key from a password using SHA-256
        """
        digest = hashlib.sha256(password.encode()).digest()
        return base64.urlsafe_b64encode(digest)

    def handle(self, *args, **options):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"inventoryhub_backup_{timestamp}.json"
            encrypted_filename = f"{filename}.enc"

            # Create temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_file:
                filepath = temp_file.name

            # Dump command
            dump_command = [
                sys.executable,
                "-X", "utf8",
                "manage.py",
                "dumpdata",
                "--exclude", "auth.permission",
                "--exclude", "contenttypes",
                "--natural-foreign",
                "--natural-primary",
                "--indent", "2"
            ]

            # Run dump
            with open(filepath, "w", encoding="utf-8") as f:
                subprocess.run(dump_command, stdout=f, stderr=subprocess.PIPE, check=True)

            # Read raw data
            with open(filepath, "rb") as f:
                raw_data = f.read()

            # 🔐 Encrypt
            key = self.derive_key(self.BACKUP_PASSWORD)
            fernet = Fernet(key)
            encrypted_data = fernet.encrypt(raw_data)

            subject = "🔐 Encrypted InventoryHub Database Backup"
            message = (
                "Hello,\n\n"
                "Attached is the encrypted backup of the InventoryHub database.\n\n"
                "To decrypt, use the agreed password.\n\n"
                "Regards,\nInventoryHub System"
            )

            recipients = [
                "itinventory@mohiafrica.org",
                "noel.langat@mohiafrica.org",
                "santana.macharia@mohiafrica.org"
            ]

            # Send email with encrypted attachment
            send_custom_email(
                subject=subject,
                message=message,
                recipient_list=recipients,
                attachment=(encrypted_filename, encrypted_data, "application/octet-stream")
            )

            # Cleanup
            os.remove(filepath)

            self.stdout.write(self.style.SUCCESS("Encrypted database backup dumped and emailed successfully."))

        except subprocess.CalledProcessError as e:
            self.stderr.write(self.style.ERROR(f"Dumpdata failed: {e.stderr.decode(errors='ignore')}"))
        except Exception as e:
            import traceback
            self.stderr.write(self.style.ERROR("Backup failed:\n" + traceback.format_exc()))
