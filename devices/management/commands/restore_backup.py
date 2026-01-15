import os
import gzip
import base64
import hashlib
import getpass
import io
import json
from cryptography.fernet import Fernet, InvalidToken
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers import deserialize
from django.db import transaction

class Command(BaseCommand):
    help = "Decrypt, decompress, and restore a database backup file"

    def add_arguments(self, parser):
        parser.add_argument("backup_file", type=str, help="Path to the .json.gz.enc backup file")

    def handle(self, *args, **options):
        backup_file = os.path.abspath(options["backup_file"])
        if not os.path.exists(backup_file):
            raise CommandError(f"File not found: {backup_file}")

        if not backup_file.endswith(".json.gz.enc"):
            raise CommandError("Backup file must end with .json.gz.enc")

        try:
            password = getpass.getpass("🔐 Enter decryption password: ")

            # DERIVE KEY
            key = hashlib.sha256(password.encode()).digest()
            key = base64.urlsafe_b64encode(key)
            cipher = Fernet(key)

            self.stdout.write("⏳ Processing backup... please wait. Do not quit the terminal.")

            # READ AND DECRYPT
            with open(backup_file, "rb") as f:
                try:
                    decrypted_data = cipher.decrypt(f.read())
                except InvalidToken:
                    raise CommandError("❌ Wrong password or corrupted file. Restore aborted.")

            # DECOMPRESS in memory
            with gzip.open(io.BytesIO(decrypted_data), 'rt', encoding='utf-8') as f:
                data = json.load(f)

            # RESTORE DATABASE directly
            with transaction.atomic():
                for obj in deserialize("json", json.dumps(data)):
                    obj.save()

            self.stdout.write(self.style.SUCCESS("✅ Database restored successfully."))

        except CommandError:
            # Reraise known errors to show clean messages
            raise
        except Exception as e:
            raise CommandError(f"Restore failed: {e}")
