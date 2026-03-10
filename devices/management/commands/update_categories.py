import re

from django.core.management.base import BaseCommand
from devices.models import Import


class Command(BaseCommand):
    help = "Split legacy 'gadget' devices into Smart Phones / Desk Phones / iPads / Tablets using keyword matching"

    def _classify(self, text: str) -> str:
        text = (text or "").lower()

        ipad_keywords = [
            "ipad",
            "i-pad",
            "i pad",
            "ipads",
            "ipad pro",
            "ipad air",
            "ipad mini",
            "apple ipad",
        ]
        if any(k in text for k in ipad_keywords):
            return "ipad"

        desk_phone_keywords = [
            "desk phone",
            "ip phone",
            "ipphone",
            "pbx phone",
            "pbx",
            "sip phone",
            "sip",
            "voip",
            "yealink",
            "grandstream",
            "avaya",
            "polycom",
            "mitel",
            "fanvil",
            "nec",
            "cisco phone",
        ]
        if any(k in text for k in desk_phone_keywords) or re.search(r"\b(ip|sip|voip|pbx)\s*phone\b", text):
            return "desk_phone"

        tablet_keywords = [
            "tablet",
            "galaxy tab",
            "matepad",
            "lenovo tab",
            "amazon fire",
            "fire hd",
            "kindle",
            "surface go",
        ]
        if any(k in text for k in tablet_keywords) or re.search(r"\btab\s*[a-z0-9\\-]*\b", text):
            return "tablet"

        smart_phone_keywords = [
            "smartphone",
            "smart phone",
            "mobile phone",
            "cell phone",
            "android",
            "iphone",
            "phone",
            "tecno",
            "infinix",
            "samsung",
            "galaxy",
            "nokia",
            "huawei",
            "oppo",
            "vivo",
            "xiaomi",
            "redmi",
            "pixel",
            "oneplus",
            "sony",
            "motorola",
            "moto",
            "itel",
        ]
        if any(k in text for k in smart_phone_keywords):
            return "smart_phone"

        # Requirement: if we can't confidently match, default to iPads.
        return "ipad"

    def handle(self, *args, **kwargs):
        self.stdout.write(
            self.style.MIGRATE_HEADING("Starting gadget split (legacy 'gadget' category only)...")
        )

        items = Import.objects.filter(category="gadget")

        total_items = items.count()
        if total_items == 0:
            self.stdout.write(self.style.WARNING("No devices found in the legacy 'gadget' category."))
            return

        self.stdout.write(f"Processing {total_items} devices...")

        updated_count = 0

        for item in items:
            text = " ".join(
                p for p in [item.device_name, item.system_model, item.processor, item.serial_number] if p
            )
            new_category = self._classify(text)

            if item.category != new_category:
                item.category = new_category
                item.save(update_fields=['category'])
                updated_count += 1

        # Summary
        self.stdout.write(
            self.style.SUCCESS(f"\nSuccessfully updated {updated_count} devices with new categories.")
        )

        self.stdout.write(self.style.SUCCESS("Gadget split complete."))

        self.stdout.write(self.style.SUCCESS("\nDone."))
