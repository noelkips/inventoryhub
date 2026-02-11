import json
from django.core.management.base import BaseCommand
from devices.models import Import, DeviceAgreement, Employee
from datetime import datetime

class Command(BaseCommand):
    help = "Dump database with normalized hardware names and include new fields/tables"

    def handle(self, *args, **kwargs):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"inventoryhub_normalized_{timestamp}.json"

        all_data = []

        # ====== EXPORT IMPORT TABLE ======
        for device in Import.objects.all():
            data = {
                "model": "devices.import",
                "pk": device.pk,
                "fields": {
                    "category": device.category,
                    "centre": device.centre.pk if device.centre else None,
                    "department": device.department.pk if device.department else None,
                    "device_name": device.device_name or device.hardware,  # normalize hardware -> device_name
                    "system_model": device.system_model,
                    "processor": device.processor,
                    "ram_gb": device.ram_gb,
                    "hdd_gb": device.hdd_gb,
                    "serial_number": device.serial_number,
                    "assignee_first_name": device.assignee_first_name,
                    "assignee_last_name": device.assignee_last_name,
                    "assignee_email_address": device.assignee_email_address,
                    "uaf_signed": getattr(device, "uaf_signed", False),  # new field
                    # keep any other fields needed
                }
            }
            all_data.append(data)

            # ===== CREATE EMPTY DEVICE AGREEMENT RECORDS =====
            if device.assignee:
                all_data.append({
                    "model": "devices.deviceagreement",
                    "pk": None,  # let Django create PK on restore
                    "fields": {
                        "device": device.pk,
                        "employee": device.assignee.pk,
                        "issuance_user_signature": "",
                        "issuance_it_signature": "",
                        "user_signed_issuance": False,
                        "it_approved_issuance": False,
                        "clearance_user_signature": "",
                        "clearance_it_signature": "",
                        "user_signed_clearance": False,
                        "it_approved_clearance": False,
                    }
                })

        # ===== SAVE JSON FILE =====
        with open(backup_filename, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)

        self.stdout.write(self.style.SUCCESS(
            f"Normalized backup created: {backup_filename}"
        ))
