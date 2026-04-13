from __future__ import annotations

from django.core.management.base import BaseCommand

from devices.utils.inventory_operational_excel import export_inventory_operational_excel


class Command(BaseCommand):
    help = (
        "Generate a practical per-centre inventory operational report as Excel "
        "with UAF compliance, missing data, duplicates, and rankings."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output",
            help="Optional output path (.xlsx). Default: reports/inventory_operational_report_<timestamp>.xlsx",
        )
        parser.add_argument(
            "--centre-code",
            action="append",
            dest="centre_codes",
            default=[],
            help="Limit report to one or more centre codes (repeat option).",
        )
        parser.add_argument(
            "--exclude-no-centre",
            action="store_true",
            help="Exclude devices that have no centre linked.",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=10,
            help="Number of centres to show per ranking metric (default: 10).",
        )

    def handle(self, *args, **options) -> None:
        centre_codes = [code.strip() for code in options["centre_codes"] if code and code.strip()]

        destination = export_inventory_operational_excel(
            output_path=options.get("output"),
            centre_codes=centre_codes or None,
            include_no_centre=not options["exclude_no_centre"],
            ranking_limit=max(1, int(options["top"])),
        )

        self.stdout.write(self.style.SUCCESS(f"Inventory operational report generated: {destination}"))
