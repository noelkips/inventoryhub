from __future__ import annotations

from typing import Any, Iterable

from django.core.management.base import BaseCommand

from devices.utils.inventory_quality_audit import (
    build_inventory_quality_report,
    write_inventory_quality_csv,
    write_inventory_quality_json,
)


class Command(BaseCommand):
    help = (
        "Audit inventory data quality per centre and compute completeness, duplicate, "
        "assignment, compliance, and quality scores."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--top",
            type=int,
            default=10,
            help="How many centres to include in ranking sections (default: 10).",
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
            help="Exclude devices not linked to a centre.",
        )
        parser.add_argument(
            "--expected-statuses",
            help="Comma-separated status values considered valid.",
        )
        parser.add_argument(
            "--expected-conditions",
            help="Comma-separated condition values considered valid.",
        )
        parser.add_argument(
            "--assigned-statuses",
            help="Comma-separated status values that imply the device is assigned/in use.",
        )
        parser.add_argument(
            "--available-statuses",
            help="Comma-separated status values that imply the device is unassigned/available.",
        )
        parser.add_argument(
            "--placeholders",
            help="Comma-separated placeholder tokens used for suspicious value checks.",
        )
        parser.add_argument(
            "--csv",
            dest="csv_output",
            help="Optional CSV output path for flattened per-centre metrics.",
        )
        parser.add_argument(
            "--json",
            dest="json_output",
            help="Optional JSON output path for full nested report.",
        )
        parser.add_argument(
            "--no-global-row",
            action="store_true",
            help="When exporting CSV, do not append the All Centres summary row.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress console tables and print only file output messages.",
        )

    def handle(self, *args, **options) -> None:
        top_n = max(1, int(options["top"]))
        centre_codes = [code.strip() for code in options["centre_codes"] if code and code.strip()]

        report = build_inventory_quality_report(
            top_n=top_n,
            centre_codes=centre_codes or None,
            include_no_centre=not options["exclude_no_centre"],
            expected_status_values=self._parse_csv_values(options.get("expected_statuses")),
            expected_condition_values=self._parse_csv_values(options.get("expected_conditions")),
            assigned_status_values=self._parse_csv_values(options.get("assigned_statuses")),
            available_status_values=self._parse_csv_values(options.get("available_statuses")),
            placeholders=self._parse_csv_values(options.get("placeholders")),
        )

        if not options["quiet"]:
            self._print_console_summary(report, top_n=top_n)

        csv_output = options.get("csv_output")
        if csv_output:
            csv_path = write_inventory_quality_csv(
                report,
                csv_output,
                include_global_row=not options["no_global_row"],
            )
            self.stdout.write(self.style.SUCCESS(f"CSV report written to: {csv_path}"))

        json_output = options.get("json_output")
        if json_output:
            json_path = write_inventory_quality_json(report, json_output)
            self.stdout.write(self.style.SUCCESS(f"JSON report written to: {json_path}"))

        if not csv_output and not json_output:
            self.stdout.write(self.style.SUCCESS("Inventory quality audit completed."))

    @staticmethod
    def _parse_csv_values(raw_value: str | None) -> list[str] | None:
        if not raw_value:
            return None
        values = [item.strip() for item in raw_value.split(",") if item.strip()]
        return values or None

    def _print_console_summary(self, report: dict[str, Any], *, top_n: int) -> None:
        global_metrics = report["global_metrics"]
        global_summary = global_metrics["summary_metrics"]
        global_scores = global_metrics["recommended_scores"]
        global_quality = global_metrics["data_quality_metrics"]

        self.stdout.write("")
        self.stdout.write("Inventory Quality Report")
        self.stdout.write(f"Generated: {report['generated_at']}")
        self.stdout.write(f"Centres in scope: {len(report['centre_reports'])}")
        self.stdout.write(f"Total devices: {global_summary['total_devices']}")
        self.stdout.write(
            "Overall score: "
            f"{global_scores['overall_inventory_quality_score']:.2f} "
            f"(completeness {global_scores['completeness_score']:.2f}, "
            f"data quality {global_scores['data_quality_score']:.2f}, "
            f"duplicate risk {global_scores['duplicate_risk_score']:.2f}, "
            f"assignment quality {global_scores['assignment_quality_score']:.2f}, "
            f"approval compliance {global_scores['approval_compliance_score']:.2f})"
        )
        self.stdout.write(
            f"Total issue count: {global_quality['total_issue_count']} "
            f"({global_quality['issues_per_device_pct']:.2f}% per device baseline)"
        )
        self.stdout.write("")

        headers = [
            "Centre",
            "Total",
            "Assigned%",
            "Approved%",
            "Disposed%",
            "DupSerial",
            "WeakDup",
            "InconsistentAssign",
            "OverallScore",
        ]
        rows = []
        for centre in report["centre_reports"]:
            summary = centre["summary_metrics"]
            duplication = centre["duplication_metrics"]
            assignment = centre["assignment_metrics"]
            scores = centre["recommended_scores"]

            centre_label = f"{centre['centre_name']} ({centre['centre_code']})"
            rows.append(
                [
                    centre_label,
                    summary["total_devices"],
                    f"{summary['assigned_devices_pct']:.2f}",
                    f"{summary['approved_devices_pct']:.2f}",
                    f"{summary['disposed_devices_pct']:.2f}",
                    duplication["duplicate_serial_numbers_per_centre"],
                    duplication["possible_weak_duplicate_devices"],
                    assignment["inconsistent_assignment_state"],
                    f"{scores['overall_inventory_quality_score']:.2f}",
                ]
            )

        self.stdout.write(self._render_table(headers, rows))
        self.stdout.write("")

        self.stdout.write(f"Top {top_n} centres with highest data quality issues")
        for item in report["rankings"]["top_centres_highest_data_quality_issues"]:
            self.stdout.write(
                f"- {item['centre_name']} ({item['centre_code']}): "
                f"{item['issue_count']} issues across {item['total_devices']} devices"
            )

        self.stdout.write("")
        self.stdout.write(f"Top {top_n} centres with highest unassigned devices")
        for item in report["rankings"]["top_centres_highest_unassigned_devices"]:
            self.stdout.write(
                f"- {item['centre_name']} ({item['centre_code']}): "
                f"{item['unassigned_devices']} unassigned devices"
            )

        self.stdout.write("")
        self.stdout.write(f"Top {top_n} centres with most duplicate serial numbers")
        for item in report["rankings"]["top_centres_most_duplicate_serial_numbers"]:
            self.stdout.write(
                f"- {item['centre_name']} ({item['centre_code']}): "
                f"{item['duplicate_serial_groups']} duplicate serial groups"
            )
        self.stdout.write("")

    @staticmethod
    def _render_table(headers: list[str], rows: list[list[Any]]) -> str:
        if not rows:
            return "No centre records found for the selected scope."

        widths = [len(header) for header in headers]
        for row in rows:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], len(str(cell)))

        def format_row(values: Iterable[Any]) -> str:
            return " | ".join(str(value).ljust(widths[index]) for index, value in enumerate(values))

        header_line = format_row(headers)
        separator = "-+-".join("-" * width for width in widths)
        body = [format_row(row) for row in rows]
        return "\n".join([header_line, separator, *body])
