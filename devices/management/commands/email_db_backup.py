import subprocess
import os
import gzip
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from devices.utils import send_custom_email
from cryptography.fernet import Fernet
import base64
import hashlib


class Command(BaseCommand):
    help = "Dump database, UTF-8 safe, compress, encrypt and email it"

    def handle(self, *args, **options):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            base_filename = f"inventoryhub_backup_{timestamp}.json"

            json_path = f"/tmp/{base_filename}"
            gz_path = f"{json_path}.gz"
            enc_path = f"{gz_path}.enc"

            # ==============================
            # 1. DUMP DATABASE (UTF-8 SAFE)
            # ==============================
            dump_cmd = [
                "python",
                "-X", "utf8",
                "manage.py",
                "dumpdata",
                "--exclude", "auth.permission",
                "--exclude", "contenttypes",
                "--natural-foreign",
                "--natural-primary",
            ]

            with open(json_path, "w", encoding="utf-8") as f:
                subprocess.check_call(dump_cmd, stdout=f)

            # ==============================
            # 2. COMPRESS
            # ==============================
            with open(json_path, "rb") as f_in:
                with gzip.open(gz_path, "wb", compresslevel=9) as f_out:
                    f_out.write(f_in.read())

            # ==============================
            # 3. ENCRYPT
            # ==============================
            password = settings.DB_BACKUP_ENCRYPTION_PASSWORD
            key = hashlib.sha256(password.encode()).digest()
            key = base64.urlsafe_b64encode(key)
            cipher = Fernet(key)

            with open(gz_path, "rb") as f:
                encrypted_data = cipher.encrypt(f.read())

            with open(enc_path, "wb") as f:
                f.write(encrypted_data)

            # ==============================
            # 4. EMAIL WITH STEPS
            # ==============================
            with open(enc_path, "rb") as f:
                enc_bytes = f.read()

            email_body = f"""
Encrypted & Compressed InventoryHub Database Backup

File: {os.path.basename(enc_path)}

RESTORE STEPS (VERY IMPORTANT):

1. Save the attached file to your project directory.

2. Run:
   python manage.py restore_backup {os.path.basename(enc_path)}

3. Enter the password when prompted (typing is hidden).

4. Wait for:
   "Database restored successfully."

NOTES:
- Do NOT rename the file.
- Do NOT unzip manually.
- Keep this file and password secure.
"""

            send_custom_email(
                subject="Encrypted InventoryHub Database Backup (Auto)",
                message=email_body,
                recipient_list=[
                    "itinventory@mohiafrica.org",
                    "noel.langat@mohiafrica.org",
                    "santana.macharia@mohiafrica.org"
                ],
                attachment=(os.path.basename(enc_path), enc_bytes, "application/octet-stream")
            )

            # ==============================
            # 5. CLEANUP
            # ==============================
            os.remove(json_path)
            os.remove(gz_path)
            os.remove(enc_path)

            self.stdout.write(self.style.SUCCESS(
                "UTF-8 safe, compressed & encrypted database backup emailed successfully."
            ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Backup failed: {e}"))
