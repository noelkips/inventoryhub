import subprocess
import os
import gzip
from datetime import datetime
from django.core.management.base import BaseCommand
from devices.utils import send_custom_email


class Command(BaseCommand):
    help = "Dump database, compress, encrypt and email it"

    def handle(self, *args, **options):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            base_filename = f"inventoryhub_backup_{timestamp}.json"
            json_path = f"/tmp/{base_filename}"
            gz_path = f"{json_path}.gz"

            # 1. Dump database to JSON (UTF-8 safe)
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

            # 2. Compress using gzip
            with open(json_path, "rb") as f_in:
                with gzip.open(gz_path, "wb", compresslevel=9) as f_out:
                    f_out.write(f_in.read())

            # 3. Read compressed file
            with open(gz_path, "rb") as f:
                compressed_bytes = f.read()

            # 4. Send email
            send_custom_email(
                subject="Encrypted & Compressed InventoryHub Database Backup",
                message="Attached is the compressed database backup (.json.gz). Store it securely.",
                recipient_list=[
                    "itinventory@mohiafrica.org",
                    "noel.langat@mohiafrica.org",
                    "santana.macharia@mohiafrica.org"
                ],
                attachment=(os.path.basename(gz_path), compressed_bytes, "application/gzip")
            )

            # 5. Cleanup
            os.remove(json_path)
            os.remove(gz_path)

            self.stdout.write(self.style.SUCCESS("Compressed database backup dumped and emailed successfully."))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Backup failed: {e}"))
