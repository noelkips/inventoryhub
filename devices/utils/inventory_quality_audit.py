from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from devices.models import Import


PLACEHOLDER_VALUES = {
    "",
    "-",
    "n/a",
    "na",
    "none",
    "null",
    "nil",
    "unknown",
    "not available",
    "nill",
}

DEFAULT_EXPECTED_STATUS_VALUES = {
    "available",
    "assigned",
    "issued",
    "in use",
    "unassigned",
    "disposed",
    "under repair",
    "repair",
    "faulty",
    "inactive",
    "active",
    "working",
    "not issued",
    "in stock",
}

DEFAULT_EXPECTED_CONDITION_VALUES = {
    "good",
    "fair",
    "poor",
    "faulty",
    "damaged",
    "working",
    "new",
    "in good condition",
    "needs repair",
    "disposed",
    "unknown",
}

DEFAULT_ASSIGNED_STATUS_VALUES = {
    "assigned",
    "issued",
    "in use",
    "active",
    "working",
}

DEFAULT_AVAILABLE_STATUS_VALUES = {
    "available",
    "unassigned",
    "not issued",
    "in stock",
}

MISSING_FIELD_NAMES = (
    "missing_device_name",
    "missing_serial_number",
    "missing_system_model",
    "missing_processor",
    "missing_ram_gb",
    "missing_hdd_gb",
    "missing_category",
    "missing_department",
)

PLACEHOLDER_SCAN_FIELDS = (
    "device_name",
    "serial_number",
    "system_model",
    "processor",
    "ram_gb",
    "hdd_gb",
    "status",
    "device_condition",
)


@dataclass
class CentreAccumulator:
    centre_id: int | None
    centre_name: str
    centre_code: str

    total_devices: int = 0
    assigned_devices: int = 0
    unassigned_devices: int = 0
    approved_devices: int = 0
    unapproved_devices: int = 0
    disposed_devices: int = 0
    active_devices: int = 0

    missing_device_name: int = 0
    missing_serial_number: int = 0
    missing_system_model: int = 0
    missing_processor: int = 0
    missing_ram_gb: int = 0
    missing_hdd_gb: int = 0
    missing_category: int = 0
    missing_department: int = 0
    missing_assignee: int = 0

    placeholder_devices: int = 0
    inconsistent_assignment_state: int = 0
    missing_approval_metadata: int = 0
    bad_status_values: int = 0
    bad_condition_values: int = 0

    duplicate_serial_groups: int = 0
    duplicate_serial_devices: int = 0
    weak_duplicate_groups: int = 0
    weak_duplicate_devices: int = 0

    category_counts: Counter[str] = field(default_factory=Counter)
    status_counts: Counter[str] = field(default_factory=Counter)
    condition_counts: Counter[str] = field(default_factory=Counter)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" .")
    return text


def humanize_normalized_value(value: str) -> str:
    if not value:
        return "Unknown"
    return " ".join(part.capitalize() for part in value.split())


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip() == ""


def is_placeholder(value: Any, placeholders: set[str]) -> bool:
    normalized = normalize_text(value)
    return normalized in placeholders


def pct(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100, 2)


def clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def parse_custom_values(values: Iterable[str] | None, default: set[str]) -> set[str]:
    if not values:
        return set(default)
    normalized = {normalize_text(item) for item in values if normalize_text(item)}
    return normalized or set(default)


def has_assignee(row: dict[str, Any]) -> bool:
    if row.get("assignee_id"):
        return True
    if not is_blank(row.get("assignee_cache")):
        return True
    if not is_blank(row.get("assignee_first_name")):
        return True
    if not is_blank(row.get("assignee_last_name")):
        return True
    if not is_blank(row.get("assignee_email_address")):
        return True
    return False


def cleaned_value_label(value: Any) -> str:
    normalized = normalize_text(value)
    if not normalized:
        return "Unknown"
    return humanize_normalized_value(normalized)


def category_label(raw_category: Any, category_display_map: dict[str, str]) -> str:
    if is_blank(raw_category):
        return "Unknown"
    raw_text = str(raw_category).strip()
    return category_display_map.get(raw_text, humanize_normalized_value(normalize_text(raw_text)))


def compute_scores(acc: CentreAccumulator) -> dict[str, float]:
    total = acc.total_devices
    if total <= 0:
        return {
            "completeness_score": 100.0,
            "data_quality_score": 100.0,
            "duplicate_risk_score": 100.0,
            "assignment_quality_score": 100.0,
            "approval_compliance_score": 100.0,
            "overall_inventory_quality_score": 100.0,
            "assignment_utilization_rate": 0.0,
        }

    missing_hits = sum(getattr(acc, field_name) for field_name in MISSING_FIELD_NAMES)
    missing_rate = missing_hits / (total * len(MISSING_FIELD_NAMES))
    placeholder_rate = acc.placeholder_devices / total
    taxonomy_rate = (acc.bad_status_values + acc.bad_condition_values) / (2 * total)

    completeness_score = clamp_score(100 - (missing_rate * 100))
    data_quality_score = clamp_score(
        100 - ((0.50 * missing_rate + 0.25 * placeholder_rate + 0.25 * taxonomy_rate) * 100)
    )

    serial_dup_rate = acc.duplicate_serial_devices / total
    weak_dup_rate = acc.weak_duplicate_devices / total
    duplicate_risk_score = clamp_score(100 - ((serial_dup_rate * 70 + weak_dup_rate * 30) * 100))
    assignment_quality_score = clamp_score(100 - ((acc.inconsistent_assignment_state / total) * 100))

    approved_total = acc.approved_devices
    if approved_total > 0:
        approval_compliance_score = clamp_score(
            100 - ((acc.missing_approval_metadata / approved_total) * 100)
        )
    else:
        approval_compliance_score = 100.0

    assignment_utilization_rate = pct(acc.assigned_devices, acc.active_devices)
    overall_inventory_quality_score = clamp_score(
        (0.35 * data_quality_score)
        + (0.25 * duplicate_risk_score)
        + (0.20 * assignment_quality_score)
        + (0.20 * approval_compliance_score)
    )

    return {
        "completeness_score": completeness_score,
        "data_quality_score": data_quality_score,
        "duplicate_risk_score": duplicate_risk_score,
        "assignment_quality_score": assignment_quality_score,
        "approval_compliance_score": approval_compliance_score,
        "overall_inventory_quality_score": overall_inventory_quality_score,
        "assignment_utilization_rate": assignment_utilization_rate,
    }


def counter_to_sorted_list(counter: Counter[str], total: int) -> list[dict[str, Any]]:
    items = sorted(counter.items(), key=lambda entry: (-entry[1], entry[0]))
    return [
        {
            "label": label,
            "count": count,
            "percentage_of_centre": pct(count, total),
        }
        for label, count in items
    ]


def center_key(centre_id: int | None) -> str:
    if centre_id is None:
        return "centre:none"
    return f"centre:{centre_id}"


def make_accumulator_for_row(row: dict[str, Any]) -> CentreAccumulator:
    return CentreAccumulator(
        centre_id=row.get("centre_id"),
        centre_name=row.get("centre__name") or "No Centre",
        centre_code=row.get("centre__centre_code") or "NO_CENTRE",
    )


def update_base_metrics(
    acc: CentreAccumulator,
    row: dict[str, Any],
    *,
    placeholders: set[str],
    expected_status_values: set[str],
    expected_condition_values: set[str],
    assigned_status_values: set[str],
    available_status_values: set[str],
    category_display_map: dict[str, str],
) -> None:
    acc.total_devices += 1

    device_is_assigned = has_assignee(row)
    if device_is_assigned:
        acc.assigned_devices += 1
    else:
        acc.unassigned_devices += 1

    if row.get("is_approved"):
        acc.approved_devices += 1
    else:
        acc.unapproved_devices += 1

    if row.get("is_disposed"):
        acc.disposed_devices += 1
    else:
        acc.active_devices += 1

    if is_blank(row.get("device_name")):
        acc.missing_device_name += 1
    if is_blank(row.get("serial_number")):
        acc.missing_serial_number += 1
    if is_blank(row.get("system_model")):
        acc.missing_system_model += 1
    if is_blank(row.get("processor")):
        acc.missing_processor += 1
    if is_blank(row.get("ram_gb")):
        acc.missing_ram_gb += 1
    if is_blank(row.get("hdd_gb")):
        acc.missing_hdd_gb += 1
    if is_blank(row.get("category")):
        acc.missing_category += 1
    if row.get("department_id") is None:
        acc.missing_department += 1
    if not device_is_assigned:
        acc.missing_assignee += 1

    if any(is_placeholder(row.get(field_name), placeholders) for field_name in PLACEHOLDER_SCAN_FIELDS):
        acc.placeholder_devices += 1

    status_normalized = normalize_text(row.get("status"))
    condition_normalized = normalize_text(row.get("device_condition"))

    if device_is_assigned and status_normalized in available_status_values:
        acc.inconsistent_assignment_state += 1
    if not device_is_assigned and status_normalized in assigned_status_values:
        acc.inconsistent_assignment_state += 1

    if row.get("is_approved") and row.get("approved_by_id") is None:
        acc.missing_approval_metadata += 1

    if status_normalized and status_normalized not in expected_status_values:
        acc.bad_status_values += 1
    if condition_normalized and condition_normalized not in expected_condition_values:
        acc.bad_condition_values += 1

    acc.category_counts[category_label(row.get("category"), category_display_map)] += 1
    acc.status_counts[cleaned_value_label(row.get("status"))] += 1
    acc.condition_counts[cleaned_value_label(row.get("device_condition"))] += 1


def center_issue_count(acc: CentreAccumulator) -> int:
    missing_hits = sum(getattr(acc, field_name) for field_name in MISSING_FIELD_NAMES)
    return (
        missing_hits
        + acc.missing_assignee
        + acc.placeholder_devices
        + acc.inconsistent_assignment_state
        + acc.missing_approval_metadata
        + acc.bad_status_values
        + acc.bad_condition_values
        + acc.duplicate_serial_devices
        + acc.weak_duplicate_devices
    )


def serialize_centre_metrics(
    acc: CentreAccumulator,
    *,
    global_duplicate_serial_groups: int,
    global_duplicate_serial_devices: int,
    global_weak_duplicate_devices: int,
    global_weak_duplicate_groups: int,
) -> dict[str, Any]:
    total = acc.total_devices
    scores = compute_scores(acc)

    summary_metrics = {
        "total_devices": total,
        "assigned_devices": acc.assigned_devices,
        "assigned_devices_pct": pct(acc.assigned_devices, total),
        "unassigned_devices": acc.unassigned_devices,
        "unassigned_devices_pct": pct(acc.unassigned_devices, total),
        "approved_devices": acc.approved_devices,
        "approved_devices_pct": pct(acc.approved_devices, total),
        "unapproved_devices": acc.unapproved_devices,
        "unapproved_devices_pct": pct(acc.unapproved_devices, total),
        "disposed_devices": acc.disposed_devices,
        "disposed_devices_pct": pct(acc.disposed_devices, total),
        "active_devices": acc.active_devices,
        "active_devices_pct": pct(acc.active_devices, total),
    }

    data_quality_metrics = {
        "devices_without_device_name": acc.missing_device_name,
        "devices_without_serial_number": acc.missing_serial_number,
        "devices_without_system_model": acc.missing_system_model,
        "devices_without_processor": acc.missing_processor,
        "devices_without_ram": acc.missing_ram_gb,
        "devices_without_storage": acc.missing_hdd_gb,
        "devices_without_category": acc.missing_category,
        "devices_without_department": acc.missing_department,
        "devices_without_assignee": acc.missing_assignee,
        "devices_with_placeholder_values": acc.placeholder_devices,
        "devices_with_placeholder_values_pct": pct(acc.placeholder_devices, total),
        "devices_with_bad_status_values": acc.bad_status_values,
        "devices_with_bad_status_values_pct": pct(acc.bad_status_values, total),
        "devices_with_bad_condition_values": acc.bad_condition_values,
        "devices_with_bad_condition_values_pct": pct(acc.bad_condition_values, total),
        "total_issue_count": center_issue_count(acc),
        "issues_per_device_pct": pct(center_issue_count(acc), total),
    }

    duplication_metrics = {
        "duplicate_serial_numbers_per_centre": acc.duplicate_serial_groups,
        "duplicate_serial_devices_per_centre": acc.duplicate_serial_devices,
        "duplicate_serial_devices_per_centre_pct": pct(acc.duplicate_serial_devices, total),
        "duplicate_serial_numbers_global": global_duplicate_serial_groups,
        "duplicate_serial_devices_global": global_duplicate_serial_devices,
        "possible_weak_duplicate_devices": acc.weak_duplicate_devices,
        "possible_weak_duplicate_devices_pct": pct(acc.weak_duplicate_devices, total),
        "possible_weak_duplicate_groups": acc.weak_duplicate_groups,
        "possible_weak_duplicate_devices_global": global_weak_duplicate_devices,
        "possible_weak_duplicate_groups_global": global_weak_duplicate_groups,
    }

    assignment_metrics = {
        "devices_without_assignee": acc.missing_assignee,
        "devices_without_assignee_pct": pct(acc.missing_assignee, total),
        "inconsistent_assignment_state": acc.inconsistent_assignment_state,
        "inconsistent_assignment_state_pct": pct(acc.inconsistent_assignment_state, total),
        "assignment_utilization_rate": scores["assignment_utilization_rate"],
    }

    compliance_metrics = {
        "approved_devices": acc.approved_devices,
        "approved_devices_pct": pct(acc.approved_devices, total),
        "unapproved_devices": acc.unapproved_devices,
        "unapproved_devices_pct": pct(acc.unapproved_devices, total),
        "missing_approval_metadata_for_approved_devices": acc.missing_approval_metadata,
        "missing_approval_metadata_for_approved_devices_pct": pct(acc.missing_approval_metadata, total),
    }

    recommended_scores = {
        "completeness_score": scores["completeness_score"],
        "data_quality_score": scores["data_quality_score"],
        "duplicate_risk_score": scores["duplicate_risk_score"],
        "assignment_quality_score": scores["assignment_quality_score"],
        "approval_compliance_score": scores["approval_compliance_score"],
        "overall_inventory_quality_score": scores["overall_inventory_quality_score"],
    }

    breakdowns = {
        "devices_by_category": counter_to_sorted_list(acc.category_counts, total),
        "devices_by_status": counter_to_sorted_list(acc.status_counts, total),
        "devices_by_condition": counter_to_sorted_list(acc.condition_counts, total),
    }

    return {
        "centre_id": acc.centre_id,
        "centre_code": acc.centre_code,
        "centre_name": acc.centre_name,
        "summary_metrics": summary_metrics,
        "data_quality_metrics": data_quality_metrics,
        "duplication_metrics": duplication_metrics,
        "assignment_metrics": assignment_metrics,
        "compliance_metrics": compliance_metrics,
        "recommended_scores": recommended_scores,
        "breakdowns": breakdowns,
    }


def build_inventory_quality_report(
    *,
    top_n: int = 10,
    centre_codes: list[str] | None = None,
    include_no_centre: bool = True,
    expected_status_values: Iterable[str] | None = None,
    expected_condition_values: Iterable[str] | None = None,
    assigned_status_values: Iterable[str] | None = None,
    available_status_values: Iterable[str] | None = None,
    placeholders: Iterable[str] | None = None,
) -> dict[str, Any]:
    """
    Build a complete inventory quality report grouped per centre.

    The report is designed for:
    - console display
    - CSV export
    - JSON/Excel transformation
    """
    normalized_placeholders = parse_custom_values(placeholders, PLACEHOLDER_VALUES)
    normalized_expected_status = parse_custom_values(
        expected_status_values, DEFAULT_EXPECTED_STATUS_VALUES
    )
    normalized_expected_condition = parse_custom_values(
        expected_condition_values, DEFAULT_EXPECTED_CONDITION_VALUES
    )
    normalized_assigned_status = parse_custom_values(
        assigned_status_values, DEFAULT_ASSIGNED_STATUS_VALUES
    )
    normalized_available_status = parse_custom_values(
        available_status_values, DEFAULT_AVAILABLE_STATUS_VALUES
    )

    category_display_map = dict(Import.CATEGORY_CHOICES)

    queryset = Import.objects.select_related("centre", "department")
    if centre_codes:
        queryset = queryset.filter(centre__centre_code__in=centre_codes)
    if not include_no_centre:
        queryset = queryset.exclude(centre__isnull=True)

    # Pull only fields needed for the audit to avoid N+1 reads and keep memory predictable.
    rows = queryset.values(
        "id",
        "centre_id",
        "centre__name",
        "centre__centre_code",
        "department_id",
        "category",
        "device_name",
        "system_model",
        "processor",
        "ram_gb",
        "hdd_gb",
        "serial_number",
        "assignee_id",
        "assignee_cache",
        "assignee_first_name",
        "assignee_last_name",
        "assignee_email_address",
        "status",
        "device_condition",
        "is_approved",
        "is_disposed",
        "approved_by_id",
    ).iterator(chunk_size=2000)

    per_centre: dict[str, CentreAccumulator] = {}
    overall = CentreAccumulator(
        centre_id=None,
        centre_name="All Centres",
        centre_code="ALL",
    )

    global_serial_groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
    centre_serial_groups: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))

    global_combo_groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    centre_combo_groups: dict[str, dict[tuple[str, str], list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )

    # Base pass: compute per-device quality and completeness metrics.
    for row in rows:
        key = center_key(row.get("centre_id"))
        if key not in per_centre:
            per_centre[key] = make_accumulator_for_row(row)
        centre_acc = per_centre[key]

        update_base_metrics(
            centre_acc,
            row,
            placeholders=normalized_placeholders,
            expected_status_values=normalized_expected_status,
            expected_condition_values=normalized_expected_condition,
            assigned_status_values=normalized_assigned_status,
            available_status_values=normalized_available_status,
            category_display_map=category_display_map,
        )
        update_base_metrics(
            overall,
            row,
            placeholders=normalized_placeholders,
            expected_status_values=normalized_expected_status,
            expected_condition_values=normalized_expected_condition,
            assigned_status_values=normalized_assigned_status,
            available_status_values=normalized_available_status,
            category_display_map=category_display_map,
        )

        row_id = int(row["id"])
        serial_normalized = normalize_text(row.get("serial_number"))
        if serial_normalized and serial_normalized not in normalized_placeholders:
            global_serial_groups[serial_normalized].append((row_id, key))
            centre_serial_groups[key][serial_normalized].append(row_id)

        model_normalized = normalize_text(row.get("system_model"))
        device_name_normalized = normalize_text(row.get("device_name"))
        if (
            model_normalized
            and device_name_normalized
            and model_normalized not in normalized_placeholders
            and device_name_normalized not in normalized_placeholders
        ):
            global_combo_groups[(key, model_normalized, device_name_normalized)].append(row_id)
            centre_combo_groups[key][(model_normalized, device_name_normalized)].append(row_id)

    # Duplicate resolution pass:
    # - strict duplicate serials (global and per-centre)
    # - weak duplicates (serial duplicates OR same model+device_name inside a centre)
    global_duplicate_serial_groups = 0
    global_duplicate_serial_ids: set[int] = set()
    centre_weak_duplicate_ids: dict[str, set[int]] = defaultdict(set)

    for serial, entries in global_serial_groups.items():
        if len(entries) <= 1:
            continue
        global_duplicate_serial_groups += 1
        for row_id, key in entries:
            global_duplicate_serial_ids.add(row_id)
            centre_weak_duplicate_ids[key].add(row_id)

    global_weak_duplicate_groups = global_duplicate_serial_groups
    global_weak_duplicate_ids: set[int] = set(global_duplicate_serial_ids)

    for group_key, group_ids in global_combo_groups.items():
        if len(group_ids) <= 1:
            continue
        global_weak_duplicate_groups += 1
        global_weak_duplicate_ids.update(group_ids)
        centre_weak_duplicate_ids[group_key[0]].update(group_ids)

    for key, acc in per_centre.items():
        serial_groups = centre_serial_groups.get(key, {})
        duplicate_groups = 0
        duplicate_ids: set[int] = set()
        for serial, serial_ids in serial_groups.items():
            if len(serial_ids) <= 1:
                continue
            duplicate_groups += 1
            duplicate_ids.update(serial_ids)
        acc.duplicate_serial_groups = duplicate_groups
        acc.duplicate_serial_devices = len(duplicate_ids)

        combo_groups = centre_combo_groups.get(key, {})
        combo_group_count = sum(1 for ids in combo_groups.values() if len(ids) > 1)

        acc.weak_duplicate_groups = acc.duplicate_serial_groups + combo_group_count
        acc.weak_duplicate_devices = len(centre_weak_duplicate_ids.get(key, set()))

    overall.duplicate_serial_groups = global_duplicate_serial_groups
    overall.duplicate_serial_devices = len(global_duplicate_serial_ids)
    overall.weak_duplicate_groups = global_weak_duplicate_groups
    overall.weak_duplicate_devices = len(global_weak_duplicate_ids)

    centre_reports = [
        serialize_centre_metrics(
            acc,
            global_duplicate_serial_groups=global_duplicate_serial_groups,
            global_duplicate_serial_devices=len(global_duplicate_serial_ids),
            global_weak_duplicate_devices=len(global_weak_duplicate_ids),
            global_weak_duplicate_groups=global_weak_duplicate_groups,
        )
        for acc in sorted(
            per_centre.values(),
            key=lambda c: (c.centre_name.casefold(), c.centre_code.casefold()),
        )
    ]

    global_report = serialize_centre_metrics(
        overall,
        global_duplicate_serial_groups=global_duplicate_serial_groups,
        global_duplicate_serial_devices=len(global_duplicate_serial_ids),
        global_weak_duplicate_devices=len(global_weak_duplicate_ids),
        global_weak_duplicate_groups=global_weak_duplicate_groups,
    )

    # Ranking payloads power admin-facing summaries and leadership dashboards.
    def ranking_payload(
        centre_report: dict[str, Any],
        metric_value: int | float,
        metric_label: str,
    ) -> dict[str, Any]:
        return {
            "centre_name": centre_report["centre_name"],
            "centre_code": centre_report["centre_code"],
            "total_devices": centre_report["summary_metrics"]["total_devices"],
            metric_label: metric_value,
        }

    top_data_issue_centres = sorted(
        (
            ranking_payload(
                report,
                report["data_quality_metrics"]["total_issue_count"],
                "issue_count",
            )
            for report in centre_reports
        ),
        key=lambda entry: (entry["issue_count"], entry["total_devices"]),
        reverse=True,
    )[:top_n]

    top_unassigned_centres = sorted(
        (
            ranking_payload(
                report,
                report["summary_metrics"]["unassigned_devices"],
                "unassigned_devices",
            )
            for report in centre_reports
        ),
        key=lambda entry: entry["unassigned_devices"],
        reverse=True,
    )[:top_n]

    top_duplicate_serial_centres = sorted(
        (
            ranking_payload(
                report,
                report["duplication_metrics"]["duplicate_serial_numbers_per_centre"],
                "duplicate_serial_groups",
            )
            for report in centre_reports
        ),
        key=lambda entry: entry["duplicate_serial_groups"],
        reverse=True,
    )[:top_n]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "centre_codes": centre_codes or [],
            "include_no_centre": include_no_centre,
        },
        "configuration": {
            "expected_status_values": sorted(normalized_expected_status),
            "expected_condition_values": sorted(normalized_expected_condition),
            "assigned_status_values": sorted(normalized_assigned_status),
            "available_status_values": sorted(normalized_available_status),
            "placeholder_values": sorted(normalized_placeholders),
        },
        "global_metrics": global_report,
        "centre_reports": centre_reports,
        "rankings": {
            "top_centres_highest_data_quality_issues": top_data_issue_centres,
            "top_centres_highest_unassigned_devices": top_unassigned_centres,
            "top_centres_most_duplicate_serial_numbers": top_duplicate_serial_centres,
        },
    }


def flatten_centre_report_row(report: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary_metrics"]
    quality = report["data_quality_metrics"]
    duplication = report["duplication_metrics"]
    assignment = report["assignment_metrics"]
    compliance = report["compliance_metrics"]
    scores = report["recommended_scores"]

    return {
        "centre_id": report["centre_id"],
        "centre_code": report["centre_code"],
        "centre_name": report["centre_name"],
        "total_devices": summary["total_devices"],
        "assigned_devices": summary["assigned_devices"],
        "assigned_devices_pct": summary["assigned_devices_pct"],
        "unassigned_devices": summary["unassigned_devices"],
        "unassigned_devices_pct": summary["unassigned_devices_pct"],
        "approved_devices": summary["approved_devices"],
        "approved_devices_pct": summary["approved_devices_pct"],
        "unapproved_devices": summary["unapproved_devices"],
        "unapproved_devices_pct": summary["unapproved_devices_pct"],
        "disposed_devices": summary["disposed_devices"],
        "disposed_devices_pct": summary["disposed_devices_pct"],
        "active_devices": summary["active_devices"],
        "active_devices_pct": summary["active_devices_pct"],
        "devices_without_device_name": quality["devices_without_device_name"],
        "devices_without_serial_number": quality["devices_without_serial_number"],
        "devices_without_system_model": quality["devices_without_system_model"],
        "devices_without_processor": quality["devices_without_processor"],
        "devices_without_ram": quality["devices_without_ram"],
        "devices_without_storage": quality["devices_without_storage"],
        "devices_without_category": quality["devices_without_category"],
        "devices_without_department": quality["devices_without_department"],
        "devices_without_assignee": quality["devices_without_assignee"],
        "devices_with_placeholder_values": quality["devices_with_placeholder_values"],
        "devices_with_placeholder_values_pct": quality["devices_with_placeholder_values_pct"],
        "devices_with_bad_status_values": quality["devices_with_bad_status_values"],
        "devices_with_bad_status_values_pct": quality["devices_with_bad_status_values_pct"],
        "devices_with_bad_condition_values": quality["devices_with_bad_condition_values"],
        "devices_with_bad_condition_values_pct": quality["devices_with_bad_condition_values_pct"],
        "duplicate_serial_numbers_per_centre": duplication["duplicate_serial_numbers_per_centre"],
        "duplicate_serial_devices_per_centre": duplication["duplicate_serial_devices_per_centre"],
        "duplicate_serial_devices_per_centre_pct": duplication["duplicate_serial_devices_per_centre_pct"],
        "duplicate_serial_numbers_global": duplication["duplicate_serial_numbers_global"],
        "duplicate_serial_devices_global": duplication["duplicate_serial_devices_global"],
        "possible_weak_duplicate_devices": duplication["possible_weak_duplicate_devices"],
        "possible_weak_duplicate_devices_pct": duplication["possible_weak_duplicate_devices_pct"],
        "possible_weak_duplicate_groups": duplication["possible_weak_duplicate_groups"],
        "inconsistent_assignment_state": assignment["inconsistent_assignment_state"],
        "inconsistent_assignment_state_pct": assignment["inconsistent_assignment_state_pct"],
        "missing_approval_metadata_for_approved_devices": compliance[
            "missing_approval_metadata_for_approved_devices"
        ],
        "missing_approval_metadata_for_approved_devices_pct": compliance[
            "missing_approval_metadata_for_approved_devices_pct"
        ],
        "assignment_utilization_rate": assignment["assignment_utilization_rate"],
        "completeness_score": scores["completeness_score"],
        "data_quality_score": scores["data_quality_score"],
        "duplicate_risk_score": scores["duplicate_risk_score"],
        "assignment_quality_score": scores["assignment_quality_score"],
        "approval_compliance_score": scores["approval_compliance_score"],
        "overall_inventory_quality_score": scores["overall_inventory_quality_score"],
        "total_issue_count": quality["total_issue_count"],
        "issues_per_device_pct": quality["issues_per_device_pct"],
    }


def write_inventory_quality_csv(
    report: dict[str, Any],
    output_path: str | Path,
    *,
    include_global_row: bool = True,
) -> Path:
    destination = Path(output_path).expanduser()
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    destination.parent.mkdir(parents=True, exist_ok=True)

    rows = [flatten_centre_report_row(row) for row in report["centre_reports"]]
    if include_global_row:
        global_row = flatten_centre_report_row(report["global_metrics"])
        global_row["centre_name"] = "All Centres"
        global_row["centre_code"] = "ALL"
        rows.append(global_row)

    if not rows:
        destination.write_text("", encoding="utf-8")
        return destination

    with destination.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return destination


def write_inventory_quality_json(report: dict[str, Any], output_path: str | Path) -> Path:
    destination = Path(output_path).expanduser()
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return destination
