from django.core.management.base import BaseCommand

from devices.utils.inventory_centre_report import export_inventory_workbook


class Command(BaseCommand):
    help = "Export devices ordered by centre into the shared IT inventory Excel format."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="IT_Inventory_All_Centres.xlsx",
            help="Where to save the Excel file.",
        )
        parser.add_argument(
            "--include-disposed",
            action="store_true",
            help="Include disposed devices in the export.",
        )
        parser.add_argument(
            "--include-unapproved",
            action="store_true",
            help="Include unapproved devices in the export.",
        )
        parser.add_argument(
            "--merge-centres",
            action="store_true",
            help="Merge centre cells for consecutive rows in the same centre.",
        )

    def handle(self, *args, **options):
        output_path, device_count = export_inventory_workbook(
            output_path=options["output"],
            include_disposed=options["include_disposed"],
            include_unapproved=options["include_unapproved"],
            merge_centres=options["merge_centres"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {device_count} devices to {output_path}"
            )
        )
