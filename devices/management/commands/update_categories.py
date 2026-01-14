# devices/management/commands/categorize_devices.py

from django.core.management.base import BaseCommand
from devices.models import Import


class Command(BaseCommand):
    help = 'Automatically categorize all Import devices based on hardware description using keyword matching'

    def handle(self, *args, **kwargs):
        self.stdout.write(
            self.style.MIGRATE_HEADING("Starting auto-categorization for ALL devices...")
        )

        # Updated keyword mapping aligned with your current CATEGORY_CHOICES
        keyword_map = {
            'laptop': [
                'laptop', 'notebook', 'macbook', 'thinkpad', 'latitude',
                'probook', 'elitebook', 'xps', 'yoga', 'zenbook', 'surface',
                'aspire', 'chromebook', 'chrome book'
            ],
            'system_unit': [
                'system unit', 'systemunit', 'desktop', 'tower', 'optiplex',
                'prodesk', 'elitedesk', 'veriton', 'inspiron', 'workstation',
                'all-in-one', 'aio', 'pc', 'cpu'
            ],
            'monitor': [
                'monitor', 'display', 'screen', 'led', 'lcd', 'p24', 'e24', 'dell monitor'
            ],
            'tv': [
                'tv', 'television', 'smart tv', 'sony', 'samsung', 'lg', 'hisense'
            ],
            'networking_devices': [
                'router', 'switch', 'access point', 'mikrotik', 'cisco',
                'tp-link', 'd-link', 'wifi', 'catalyst', 'ubiquiti', 'ap', 'wlc'
            ],
            'printer': [
                'printer', 'laserjet', 'deskjet', 'mfp', 'scanner', 'copier',
                'epson', 'canon', 'kyocera', 'photocopier', 'ricoh'
            ],
            'n_computing': [
                'n-computing', 'n computing', 'ncomputing', 'l300k',
                'thin client', 'terminal', 'zero client', 'n-compute'
            ],
            'projector': [
                'projector', 'proj'
            ],
            'gadget': [
                'phone', 'iphone', 'android', 'tablet', 'ipad', 'ipads',
                'smartphone', 'tecno', 'infinix', 'samsung a', 'samsung s'
            ],
            'access_point': [
                'access point', 'ap ', 'wap', 'wireless ap'
            ],
            'power_backup_equipment': [
                'ups', 'power backup', 'stabilizer', 'inverter', 'battery backup'
            ],
        }

        # Get all devices with non-empty hardware
        items = Import.objects.exclude(
            hardware__isnull=True
        ).exclude(
            hardware__exact=''
        )

        total_items = items.count()
        if total_items == 0:
            self.stdout.write(self.style.WARNING("No devices with hardware description found."))
            return

        self.stdout.write(f"Processing {total_items} devices...")

        updated_count = 0
        unmatched = []

        for item in items:
            hw_lower = item.hardware.lower().strip()
            found_category = None

            # Search for matching category
            for category, keywords in keyword_map.items():
                if any(keyword in hw_lower for keyword in keywords):
                    found_category = category
                    break

            if found_category and item.category != found_category:
                item.category = found_category
                item.save(update_fields=['category'])
                updated_count += 1
            elif not found_category:
                unmatched.append(item)

        # Summary
        self.stdout.write(
            self.style.SUCCESS(f"\nSuccessfully updated {updated_count} devices with new categories.")
        )

        if unmatched:
            self.stdout.write(
                self.style.WARNING(f"\n{len(unmatched)} devices could not be auto-categorized:")
            )
            self.stdout.write(
                f"{'ID':<6} | {'Hardware':<50} | {'Serial':<20} | {'Current Category'}"
            )
            self.stdout.write("-" * 100)
            for item in unmatched[:50]:  # Limit output to avoid flooding console
                hw_display = (item.hardware or "")[:50]
                serial = (item.serial_number or "")[:20]
                current_cat = item.get_category_display() if item.category else "None"
                self.stdout.write(f"{item.pk:<6} | {hw_display:<50} | {serial:<20} | {current_cat}")
            if len(unmatched) > 50:
                self.stdout.write(f"... and {len(unmatched) - 50} more.")
        else:
            self.stdout.write(self.style.SUCCESS("All devices were successfully categorized!"))

        self.stdout.write(self.style.SUCCESS("\nCategorization complete!"))