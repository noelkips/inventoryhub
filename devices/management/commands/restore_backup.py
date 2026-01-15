import os
import gzip
import base64
import hashlib
import getpass
from cryptography.fernet import Fernet
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command


class Command(BaseCommand):
    help = "Decrypt, decompress and restore a database backup file"

    def add_arguments(self, parser):
        parser.add_argument(
            "backup_file",
            type=str,
            help="Path to the .json.gz.enc backup file"
        )

    def handle(self, *args, **options):
        backup_file = options["backup_file"]

        if not os.path.exists(backup_file):
            raise CommandError(f"File not found: {backup_file}")

        if not backup_file.endswith(".json.gz.enc"):
            raise CommandError("Backup file must end with .json.gz.enc")

        try:
            self.stdout.write("🔐 Enter decryption password:")
            password = getpass.getpass("")  # hidden input

            # ==============================
            # 1. DERIVE KEY
            # ==============================
            key = hashlib.sha256(password.encode()).digest()
            key = base64.urlsafe_b64encode(key)
            cipher = Fernet(key)

            # ==============================
            # 2. DECRYPT
            # ==============================
            self.stdout.write("🔓 Decrypting backup...")
            with open(backup_file, "rb") as f:
                encrypted_data = f.read()

            decrypted_data = cipher.decrypt(encrypted_data)

            gz_path = backup_file.replace(".enc", "")
            with open(gz_path, "wb") as f:
                f.write(decrypted_data)

            # ==============================
            # 3. DECOMPRESS
            # ==============================
            self.stdout.write("📦 Decompressing backup...")
            json_path = gz_path.replace(".gz", "")

            with gzip.open(gz_path, "rb") as f_in:
                with open(json_path, "wb") as f_out:
                    f_out.write(f_in.read())

            # ==============================
            # 4. LOAD DATA
            # ==============================
            self.stdout.write("🗄️  Restoring database...")
            call_command("loaddata", json_path)

            # ==============================
            # 5. CLEANUP
            # ==============================
            os.remove(gz_path)
            os.remove(json_path)

            self.stdout.write(self.style.SUCCESS(
                "✅ Database restored successfully."
            ))

        except Exception as e:
            raise CommandError(f"Restore failed: {e}")
