import logging
from datetime import datetime, timedelta
from io import BytesIO

import xlsxwriter
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator

from django.db import IntegrityError, transaction
from django.db.models import (
    Q, Count, F, Exists, OuterRef, ExpressionWrapper, DurationField
)
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

from .models import PPMPeriod, PPMActivity, PPMTask
from devices.models import Import, Centre, DeviceLog

logger = logging.getLogger(__name__)


def is_superuser(user):
    return user.is_superuser


# ----------------------------
# Helpers (Employee alignment)
# ----------------------------
def _device_assignee_name(device: Import) -> str:
    """
    Prefer Employee model (Import.assignee), fallback to legacy fields.
    """
    if getattr(device, "assignee", None):
        try:
            return device.assignee.full_name or str(device.assignee)
        except Exception:
            return str(device.assignee)

    first = (getattr(device, "assignee_first_name", "") or "").strip()
    last = (getattr(device, "assignee_last_name", "") or "").strip()
    name = f"{first} {last}".strip()
    return name or "N/A"


def _device_assignee_email(device: Import) -> str:
    if getattr(device, "assignee", None) and getattr(device.assignee, "email", None):
        return device.assignee.email or "N/A"
    legacy = (getattr(device, "assignee_email_address", "") or "").strip()
    return legacy or "N/A"


def _attach_display_fields_to_device(device: Import) -> None:
    """
    Adds template-friendly fields on the instance.
    (Doesn't touch DB; just for rendering.)
    """
    device.assignee_name = _device_assignee_name(device)
    device.assignee_email = _device_assignee_email(device)


def _attach_display_fields_to_task(task: PPMTask) -> None:
    device = getattr(task, "device", None)
    if device:
        _attach_display_fields_to_device(device)
        task.assignee_name = device.assignee_name
        task.assignee_email = device.assignee_email
    else:
        task.assignee_name = "N/A"
        task.assignee_email = "N/A"


def _build_device_log_message(*, period_name: str, no_activity: bool, activities: list[str], reason: str, notes: str) -> str:
    prefix = f"PPM ({period_name})"
    if no_activity:
        msg = f"{prefix}: NO activity performed."
        if reason:
            msg += f" Reason: {reason}"
        if notes:
            msg += f" | Notes: {notes}"
        return msg

    msg = f"{prefix}: Activities performed: " + (", ".join(activities) if activities else "N/A")
    if notes:
        msg += f" | Notes: {notes}"
    return msg


# ----------------------------
# Views
# ----------------------------

@user_passes_test(is_superuser)
def ppm_device_list(request):
    centres = Centre.objects.all()
    search_query = request.GET.get("search", "").strip()
    centre_filter = request.GET.get("centre", "")
    ppm_status_filter = request.GET.get("ppm_status", "")

    try:
        items_per_page = int(request.GET.get("items_per_page", 10))
        if items_per_page not in [10, 25, 50, 100]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    active_period = PPMPeriod.objects.filter(is_active=True).first()

    if not active_period:
        devices = Import.objects.none()
        messages.warning(request, "No active PPM period. Please create and activate a period.")
    else:
        devices = Import.objects.select_related("centre", "department", "assignee").all()

        ppm_task_exists = PPMTask.objects.filter(device=OuterRef("pk"), period=active_period)
        devices = devices.annotate(has_ppm_task=Exists(ppm_task_exists))

        if search_query:
            devices = devices.filter(
                Q(serial_number__icontains=search_query)
                | Q(assignee_cache__icontains=search_query)
                | Q(assignee__first_name__icontains=search_query)
                | Q(assignee__last_name__icontains=search_query)
                | Q(assignee__email__icontains=search_query)
                | Q(assignee__staff_number__icontains=search_query)
                | Q(assignee_first_name__icontains=search_query)
                | Q(assignee_last_name__icontains=search_query)
                | Q(assignee_email_address__icontains=search_query)
                | Q(department__name__icontains=search_query)
                | Q(device_name__icontains=search_query)
                | Q(system_model__icontains=search_query)
                | Q(processor__icontains=search_query)
            )

        if centre_filter:
            devices = devices.filter(centre_id=centre_filter)

        if ppm_status_filter == "done":
            devices = devices.filter(has_ppm_task=True)
        elif ppm_status_filter == "not_done":
            devices = devices.filter(has_ppm_task=False)

    from django.core.paginator import Paginator
    paginator = Paginator(devices, items_per_page)
    page_number = request.GET.get("page", 1)
    try:
        devices_page = paginator.page(page_number)
    except Exception:
        devices_page = paginator.page(1)

    for d in devices_page:
        _attach_display_fields_to_device(d)

    activities = active_period.activities.all() if active_period else []

    page_range = []
    if paginator.num_pages > 1:
        start = max(1, devices_page.number - 2)
        end = min(paginator.num_pages + 1, devices_page.number + 3)
        page_range = list(range(start, end))
        if start > 2:
            page_range = [1, None] + page_range
        elif start == 2:
            page_range = [1] + page_range
        if end < paginator.num_pages:
            page_range = page_range + [None, paginator.num_pages]
        elif end == paginator.num_pages:
            page_range = page_range + [paginator.num_pages]

    report_data = {
        "search_query": search_query,
        "centre_filter": centre_filter,
        "ppm_status_filter": ppm_status_filter,
        "items_per_page": items_per_page,
        "total_records": paginator.count,
    }

    context = {
        "devices": devices_page,
        "report_data": report_data,
        "centres": centres,
        "activities": activities,
        "active_period": active_period,
        "items_per_page_options": [10, 25, 50, 100],
        "page_range": page_range,
        "view_name": "ppm_device_list",
    }
    return render(request, "ppm/ppm_device_list.html", context)



def ppm_task_create(request, device_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request method."}, status=400)

    try:
        device = get_object_or_404(Import, id=device_id)
        active_period = PPMPeriod.objects.filter(is_active=True).first()
        if not active_period:
            return JsonResponse({"success": False, "error": "No active PPM period."}, status=400)

        # ✅ Support both field names (template uses notes, older code uses remarks)
        notes = (request.POST.get("notes") or request.POST.get("remarks") or "").strip()

        completed_date_raw = (request.POST.get("completed_date") or "").strip()
        completed_date = None
        if completed_date_raw:
            try:
                completed_date = datetime.strptime(completed_date_raw, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"success": False, "error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

        no_activity = request.POST.get("no_ppm_activity_performed") in ["on", "true", "1", True]
        reason = (request.POST.get("reason") or "").strip()

        activities_ids = request.POST.getlist("activities")

        # ✅ Validation depending on mode
        if no_activity:
            if not reason:
                return JsonResponse({"success": False, "error": "Reason is required when no activity is performed."}, status=400)
        else:
            if not activities_ids:
                return JsonResponse({"success": False, "error": "Select at least one activity OR enable 'No activity performed'."}, status=400)

            try:
                activities_ids = [int(x) for x in activities_ids]
            except ValueError:
                return JsonResponse({"success": False, "error": "Invalid activity IDs."}, status=400)

            valid_count = PPMActivity.objects.filter(id__in=activities_ids).count()
            if valid_count != len(activities_ids):
                return JsonResponse({"success": False, "error": "One or more selected activities do not exist."}, status=400)

        with transaction.atomic():
            existing_task = PPMTask.objects.filter(device=device, period=active_period).first()
            is_new = False

            if existing_task:
                ppm_task = existing_task
            else:
                ppm_task = PPMTask.objects.create(
                    device=device,
                    period=active_period,
                    created_by=request.user,
                )
                is_new = True

            # ✅ Update common fields
            ppm_task.completed_date = completed_date

            # ✅ Handle model fields safely (in case names differ slightly in your project)
            # Prefer storing notes in "remarks" since your model snapshot uses remarks
            if hasattr(ppm_task, "remarks"):
                ppm_task.remarks = notes
            elif hasattr(ppm_task, "notes"):
                ppm_task.notes = notes

            if hasattr(ppm_task, "no_ppm_activity_performed"):
                ppm_task.no_ppm_activity_performed = bool(no_activity)

            if hasattr(ppm_task, "reason"):
                ppm_task.reason = reason if no_activity else ""

            ppm_task.save()

            # ✅ Activities logic
            if no_activity:
                ppm_task.activities.clear()
            else:
                ppm_task.activities.set(activities_ids)

            # ✅ DEVICE LOG (this is where your earlier crash likely was)
            # DeviceLog fields: device, user, message, created_at, ppm_task, ppm_attempt
            try:
                if no_activity:
                    msg = f"PPM marked as NOT DONE for period '{active_period.name}'. Reason: {reason}"
                else:
                    acts = list(PPMActivity.objects.filter(id__in=activities_ids).values_list("name", flat=True))
                    msg = f"PPM {'created' if is_new else 'updated'} for period '{active_period.name}'. Activities: {', '.join(acts)}"

                DeviceLog.objects.create(
                    device=device,
                    user=request.user,
                    message=msg,
                    ppm_task=ppm_task,
                    ppm_attempt=None,
                )
            except Exception as log_err:
                # don’t break saving if logging fails
                logger.exception("DeviceLog creation failed: %s", log_err)

        messages.success(request, f'PPM task {"created" if is_new else "updated"} successfully for {device.serial_number}!')

        return JsonResponse({
            "success": True,
            "is_new": is_new,
            "device_name": device.serial_number,
        })

    except IntegrityError as e:
        return JsonResponse({"success": False, "error": f"Database error: {str(e)}"}, status=400)
    except Exception as e:
        logger.exception("Error in ppm_task_create: %s", e)
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


@user_passes_test(is_superuser)
def get_ppm_task(request, device_id):
    try:
        device = get_object_or_404(Import, id=device_id)
        active_period = PPMPeriod.objects.filter(is_active=True).first()
        if not active_period:
            return JsonResponse({"error": "No active PPM period."}, status=400)

        data = {
            "device_name": device.device_name or "",
            "system_model": device.system_model or "",
            "processor": device.processor or "",
            "ram_gb": device.ram_gb or "",
            "hdd_gb": device.hdd_gb or "",
        }

        task = PPMTask.objects.filter(device_id=device_id, period=active_period).first()
        if task:
            # ✅ read safely even if your model field names differ
            no_act = bool(getattr(task, "no_ppm_activity_performed", False))
            reason = getattr(task, "reason", "") or ""

            # notes could be stored as remarks or notes depending on your model
            notes_val = ""
            if hasattr(task, "notes"):
                notes_val = task.notes or ""
            elif hasattr(task, "remarks"):
                notes_val = task.remarks or ""

            data.update({
                "activities": list(task.activities.values_list("id", flat=True)),
                "completed_date": task.completed_date.strftime("%Y-%m-%d") if task.completed_date else "",
                "remarks": notes_val,  # keep for backward compatibility with your JS
                "notes": notes_val,    # also provide notes explicitly
                "no_ppm_activity_performed": no_act,  # ✅ THIS is what your modal needs
                "reason": reason,                   # ✅ and this too
            })

        return JsonResponse(data)

    except Exception as e:
        logger.exception("Error in get_ppm_task: %s", e)
        return JsonResponse({"error": "An unexpected error occurred."}, status=500)

@login_required
def ppm_history(request, device_id=None):
    tasks = (
        PPMTask.objects.select_related(
            "device",
            "device__centre",
            "device__department",
            "device__assignee",
            "period",
            "created_by",
        )
        .prefetch_related("activities")
        .order_by("-updated_at", "-created_at")
    )

    # Permissions
    if not request.user.is_superuser:
        if getattr(request.user, "centre", None):
            tasks = tasks.filter(device__centre=request.user.centre)
        else:
            tasks = PPMTask.objects.none()

    if device_id:
        tasks = tasks.filter(device__id=device_id)

    # Filters
    search_query = request.GET.get("search", "").strip()
    centre_filter = request.GET.get("centre", "").strip()

    if search_query:
        tasks = tasks.filter(
            Q(device__serial_number__icontains=search_query)
            | Q(device__device_name__icontains=search_query)
            | Q(device__department__name__icontains=search_query)
            | Q(device__assignee_first_name__icontains=search_query)
            | Q(device__assignee_last_name__icontains=search_query)
            | Q(device__assignee_email_address__icontains=search_query)
            | Q(created_by__first_name__icontains=search_query)
            | Q(created_by__last_name__icontains=search_query)
            | Q(created_by__email__icontains=search_query)
        )

    if centre_filter:
        tasks = tasks.filter(device__centre_id=centre_filter)

    # Pagination
    try:
        items_per_page = int(request.GET.get("items_per_page", 10))
        if items_per_page not in [10, 25, 50, 100]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    paginator = Paginator(tasks, items_per_page)
    page_number = request.GET.get("page", 1)
    try:
        tasks_on_page = paginator.page(page_number)
    except Exception:
        tasks_on_page = paginator.page(1)

    # ✅ IMPORTANT: attach display fields (assignee_name/assignee_email)
    for t in tasks_on_page:
        _attach_display_fields_to_task(t)

    centres = Centre.objects.all() if request.user.is_superuser else (
        Centre.objects.filter(id=request.user.centre.id) if getattr(request.user, "centre", None) else Centre.objects.none()
    )

    # Custom page range
    page_range = []
    if paginator.num_pages > 1:
        start = max(1, tasks_on_page.number - 2)
        end = min(paginator.num_pages + 1, tasks_on_page.number + 3)
        page_range = list(range(start, end))
        if start > 2:
            page_range = [1, None] + page_range
        elif start == 2:
            page_range = [1] + page_range
        if end < paginator.num_pages:
            page_range = page_range + [None, paginator.num_pages]
        elif end == paginator.num_pages:
            page_range = page_range + [paginator.num_pages]

    report_data = {
        "total_records": paginator.count,
        "search_query": search_query,
        "items_per_page": items_per_page,
        "centre_filter": centre_filter,
    }

    context = {
        "tasks": tasks_on_page,
        "device_id": device_id,
        "centres": centres,
        "items_per_page_options": [10, 25, 50, 100],
        "report_data": report_data,
        "page_range": page_range,
        "view_name": "ppm_history",
    }
    return render(request, "ppm/ppm_history.html", context)


@login_required
def ppm_task_detail(request, task_id):
    qs = (
        PPMTask.objects.select_related(
            "device",
            "device__centre",
            "device__department",
            "device__assignee",
            "period",
            "created_by",
        )
        .prefetch_related("activities")
    )
    task = get_object_or_404(qs, id=task_id)

    # Permissions
    if not request.user.is_superuser:
        if not getattr(request.user, "centre", None) or task.device.centre_id != request.user.centre_id:
            return JsonResponse({"success": False, "error": "Permission denied."}, status=403)

    # ✅ attach assignee display for consistency
    _attach_display_fields_to_task(task)

    no_act = bool(getattr(task, "no_ppm_activity_performed", False))
    reason = (getattr(task, "reason", "") or "").strip()
    remarks = (getattr(task, "remarks", "") or getattr(task, "notes", "") or "").strip()

    activities = list(task.activities.values("id", "name"))

    created_by_name = "N/A"
    if task.created_by:
        created_by_name = (
            f"{(task.created_by.first_name or '').strip()} {(task.created_by.last_name or '').strip()}".strip()
            or (task.created_by.email or "N/A")
        )

    return JsonResponse({
        "success": True,
        "task": {
            "id": task.id,
            "device_serial": task.device.serial_number,
            "device_name": getattr(task.device, "device_name", "") or "",
            "period": task.period.name if task.period else "",
            "completed_date": task.completed_date.strftime("%Y-%m-%d") if task.completed_date else "",
            "created_at": task.created_at.strftime("%Y-%m-%d %H:%M") if task.created_at else "",
            "updated_at": task.updated_at.strftime("%Y-%m-%d %H:%M") if task.updated_at else "",
            "centre": task.device.centre.name if task.device.centre else "",
            "department": task.device.department.name if getattr(task.device, "department", None) else "",
            "assignee": getattr(task, "assignee_name", "N/A") or "N/A",
            "created_by": created_by_name,
            "no_activity": no_act,
            "reason": reason,
            "remarks": remarks,
            "activities": activities,
        }
    })
@login_required
def ppm_report(request):
    import logging
    from io import BytesIO
    from datetime import timedelta

    import xlsxwriter
    from django.db.models import Count, Q, F, DurationField, ExpressionWrapper
    from django.http import HttpResponse
    from django.shortcuts import redirect, render
    from django.utils import timezone
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    logger = logging.getLogger(__name__)

    if request.user.is_superuser:
        centres = Centre.objects.all()
        device_query = Import.objects.select_related("centre", "department", "assignee").all()
        base_tasks_query = (
            PPMTask.objects.select_related(
                "device",
                "device__centre",
                "device__department",
                "device__assignee",
                "period",
                "created_by",
            ).prefetch_related("activities")
        )
    elif getattr(request.user, "centre", None):
        centres = Centre.objects.filter(id=request.user.centre.id)
        device_query = (
            Import.objects.select_related("centre", "department", "assignee")
            .filter(centre=request.user.centre)
        )
        base_tasks_query = (
            PPMTask.objects.filter(device__centre=request.user.centre)
            .select_related(
                "device",
                "device__centre",
                "device__department",
                "device__assignee",
                "period",
                "created_by",
            )
            .prefetch_related("activities")
        )
    else:
        centres = Centre.objects.none()
        device_query = Import.objects.none()
        base_tasks_query = PPMTask.objects.none()

    periods = PPMPeriod.objects.all().order_by("-start_date")

    period_filter = request.GET.get("period", "")
    centre_filter = request.GET.get("centre", "")
    search_query = request.GET.get("search", "").strip()
    items_per_page = request.GET.get("items_per_page", "10")
    page_number = request.GET.get("page", "1")
    export_type = request.GET.get("export", "")

    # Default period selection
    current_period = None
    if not period_filter:
        active_period = PPMPeriod.objects.filter(is_active=True).first()
        if active_period:
            period_filter = str(active_period.id)
        else:
            latest_period = PPMPeriod.objects.order_by("-end_date").first()
            if latest_period:
                period_filter = str(latest_period.id)

    if period_filter:
        try:
            current_period = PPMPeriod.objects.get(id=period_filter)
        except PPMPeriod.DoesNotExist:
            messages.error(request, "Invalid period selected.")
            return redirect("ppm_report")

    try:
        items_per_page = int(items_per_page)
        if items_per_page not in [10, 25, 50, 100, 500]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    try:
        page_number = int(page_number) if page_number else 1
    except ValueError:
        page_number = 1

    # Centre filter
    if centre_filter and (request.user.is_superuser or str(getattr(request.user.centre, "id", "")) == centre_filter):
        device_query = device_query.filter(centre__id=centre_filter)

    approved_devices = device_query.filter(is_approved=True, is_disposed=False).count()

    devices_with_ppm = 0
    devices_without_ppm = 0
    ppm_completion_rate = 0
    completed_on_time = 0
    overdue_tasks = 0
    tasks_due_soon = 0
    is_past_period = False
    avg_completion_time = None
    ppm_status_labels = []
    ppm_status_data = []
    ppm_status_colors = []
    ppm_tasks_by_activity = []
    ppm_by_centre = []
    tasks_query = base_tasks_query

    # ✅ New metrics for tasks
    total_ppm_tasks = 0
    tasks_done = 0
    tasks_not_done = 0

    # --- Assignee: NO fallback (only relation) ---
    def _assignee_name(task: PPMTask) -> str:
        a = getattr(getattr(task, "device", None), "assignee", None)
        if not a:
            return "N/A"
        try:
            full = (a.get_full_name() or "").strip()
        except Exception:
            full = ""
        if full:
            return full
        first = (getattr(a, "first_name", "") or "").strip()
        last = (getattr(a, "last_name", "") or "").strip()
        name = f"{first} {last}".strip()
        return name or (getattr(a, "email", "") or "N/A")

    def _assignee_email(task: PPMTask) -> str:
        a = getattr(getattr(task, "device", None), "assignee", None)
        return (getattr(a, "email", "") or "").strip() or "N/A"

    if current_period:
        tasks_query = base_tasks_query.filter(period=current_period)

        if centre_filter and (request.user.is_superuser or str(getattr(request.user.centre, "id", "")) == centre_filter):
            tasks_query = tasks_query.filter(device__centre__id=centre_filter)

        # ✅ Search ONLY relational assignee fields (no legacy caches)
        if search_query:
            tasks_query = tasks_query.filter(
                Q(device__serial_number__icontains=search_query)
                | Q(device__device_name__icontains=search_query)
                | Q(device__department__name__icontains=search_query)
                | Q(remarks__icontains=search_query)
                | Q(device__assignee__first_name__icontains=search_query)
                | Q(device__assignee__last_name__icontains=search_query)
                | Q(device__assignee__email__icontains=search_query)
                | Q(device__assignee__staff_number__icontains=search_query)
            )

        total_ppm_tasks = tasks_query.count()

        # ✅ Task metrics
        tasks_not_done = tasks_query.filter(no_ppm_activity_performed=True).count()
        tasks_done = tasks_query.filter(no_ppm_activity_performed=False, completed_date__isnull=False).count()

        devices_with_ppm = tasks_query.values("device").distinct().count()
        devices_without_ppm = approved_devices - devices_with_ppm
        ppm_completion_rate = round((devices_with_ppm / approved_devices * 100) if approved_devices > 0 else 0, 1)

        now = timezone.now().date()
        is_past_period = current_period.end_date < now
        overdue_tasks = devices_without_ppm if is_past_period else 0

        seven_days_ahead = now + timedelta(days=7)
        if current_period.end_date <= seven_days_ahead and current_period.end_date >= now:
            tasks_due_soon = devices_without_ppm

        completed_on_time = tasks_query.filter(
            completed_date__lte=current_period.end_date, completed_date__isnull=False
        ).values("device").distinct().count()

        completed_with_time = tasks_query.filter(completed_date__isnull=False).annotate(
            days_to_complete=ExpressionWrapper(F("completed_date") - F("period__start_date"), output_field=DurationField())
        )
        if completed_with_time.exists():
            total_days = sum(t.days_to_complete.days for t in completed_with_time if t.days_to_complete)
            avg_completion_time = round(total_days / completed_with_time.count(), 1)

        if not is_past_period:
            ppm_status_labels = ["PPM Done", "PPM Not Done"]
            ppm_status_data = [devices_with_ppm, devices_without_ppm]
            ppm_status_colors = ["#10B981", "#F59E0B"]
        else:
            ppm_status_labels = ["PPM Done", "PPM Overdue"]
            ppm_status_data = [devices_with_ppm, devices_without_ppm]
            ppm_status_colors = ["#10B981", "#EF4444"]

        ppm_tasks_by_activity = (
            tasks_query.values("activities__name").annotate(count=Count("id")).order_by("-count")
            if tasks_query.exists()
            else []
        )

    centres_to_show = centres if not centre_filter else centres.filter(id=centre_filter)
    ppm_by_centre = []
    for centre in centres_to_show:
        centre_device_query = device_query.filter(centre=centre)
        centre_approved = centre_device_query.filter(is_approved=True, is_disposed=False).count()
        centre_with_ppm = (
            base_tasks_query.filter(period=current_period, device__centre=centre).values("device").distinct().count()
            if current_period
            else 0
        )
        if centre_approved > 0:
            ppm_by_centre.append(
                {"device__centre__name": centre.name, "total": centre_approved, "completed": centre_with_ppm}
            )
    ppm_by_centre = sorted(ppm_by_centre, key=lambda x: x.get("completed", 0), reverse=True)

    device_condition_breakdown = (
        device_query.filter(is_approved=True, is_disposed=False)
        .values("device_condition")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    recent_ppm_completions = tasks_query.filter(completed_date__isnull=False).order_by("-completed_date")[:10]

    # ✅ Exports
    if export_type in ["pdf", "excel"]:
        export_tasks = list(tasks_query.order_by("-created_at", "id"))
        if approved_devices == 0:
            messages.error(request, "No data available for the selected filters.")
            return redirect("ppm_report")

        centre_obj = centres.get(id=centre_filter) if centre_filter else None

        # ---------- PDF ----------
        if export_type == "pdf":
            response = HttpResponse(content_type="application/pdf")
            filename = f"PPM_Report_{current_period.name if current_period else 'All'}_{centre_obj.name if centre_obj else 'All'}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'

            doc = SimpleDocTemplate(
                response,
                pagesize=landscape(A4),
                rightMargin=8 * mm,
                leftMargin=8 * mm,
                topMargin=12 * mm,
                bottomMargin=12 * mm,
            )

            elements = []
            styles = getSampleStyleSheet()

            styles.add(ParagraphStyle(
                name="ReportTitle",
                fontSize=14,
                leading=16,
                textColor=colors.HexColor("#143C50"),
                alignment=1,
                spaceAfter=4,
            ))
            styles.add(ParagraphStyle(
                name="SubTitle",
                fontSize=9,
                leading=11,
                textColor=colors.HexColor("#143C50"),
                alignment=1,
                spaceAfter=6,
            ))
            styles.add(ParagraphStyle(name="Cell", fontSize=7.5, leading=9.2, wordWrap="CJK"))
            styles.add(ParagraphStyle(name="CellSmall", fontSize=6.8, leading=8.5, wordWrap="CJK"))

            # ✅ Tag text style (inside chip)
            styles.add(ParagraphStyle(
                name="TagText",
                fontSize=6.6,
                leading=8.0,
                textColor=colors.HexColor("#1D4ED8"),
                wordWrap="CJK",
            ))
            styles.add(ParagraphStyle(
                name="TagTextDanger",
                fontSize=6.6,
                leading=8.0,
                textColor=colors.HexColor("#B91C1C"),
                wordWrap="CJK",
            ))
            styles.add(ParagraphStyle(
                name="NoteText",
                fontSize=7.0,
                leading=9.0,
                textColor=colors.HexColor("#111827"),
                wordWrap="CJK",
            ))

            def _build_activity_tag_grid(activity_names, *, max_cols=4):
                """
                Creates a grid of 'chips' using a nested Table.
                Keeps everything wrapped to avoid overflow.
                """
                if not activity_names:
                    return None

                # Build rows
                rows = []
                row = []
                for name in activity_names:
                    row.append(name)
                    if len(row) == max_cols:
                        rows.append(row)
                        row = []
                if row:
                    while len(row) < max_cols:
                        row.append("")
                    rows.append(row)

                data = []
                for r in rows:
                    data.append([
                        Paragraph(n, styles["TagText"]) if n else "" for n in r
                    ])

                # Inner table: fixed chip column widths (do NOT affect your outer colWidths)
                inner = Table(
                    data,
                    colWidths=[28 * mm] * max_cols,  # wraps inside each chip
                    hAlign="LEFT",
                )
                inner.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),

                    # Chip background + border
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
                    ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#DBEAFE")),

                    # Add a little spacing between chips
                    ("GRID", (0, 0), (-1, -1), 4, colors.white),
                ]))
                return inner

            def _no_activity_chip():
                chip = Table([[Paragraph("NO ACTIVITY", styles["TagTextDanger"])]], colWidths=[40 * mm])
                chip.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEE2E2")),
                    ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#FCA5A5")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                return chip

            elements.append(Paragraph("MOHI IT - PPM REPORT", styles["ReportTitle"]))

            if current_period:
                elements.append(Paragraph(
                    f"Period: {current_period.name} ({current_period.start_date} to {current_period.end_date})",
                    styles["SubTitle"]
                ))

            elements.append(Paragraph(
                f"Generated: {timezone.now().strftime('%B %d, %Y at %I:%M %p')}",
                styles["SubTitle"]
            ))

            if centre_obj:
                elements.append(Paragraph(f"Centre: {centre_obj.name}", styles["SubTitle"]))

            elements.append(Paragraph(
                f"Total Tasks: {total_ppm_tasks} • Done: {tasks_done} • Not Done: {tasks_not_done}",
                styles["SubTitle"]
            ))
            elements.append(Spacer(1, 6))

            table_data = [[
                "Device / Period",
                "Status / Completed",
                "Centre",
                "Assignee",
                "Activities / Notes",
            ]]

            for t in export_tasks:
                serial = getattr(t.device, "serial_number", "") or "N/A"
                dname = getattr(t.device, "device_name", "") or "N/A"
                period_name = t.period.name if t.period else "N/A"

                status = "Not Done" if getattr(t, "no_ppm_activity_performed", False) else ("Completed" if t.completed_date else "Open")
                completed = t.completed_date.strftime("%Y-%m-%d") if t.completed_date else "-"

                centre_name = t.device.centre.name if getattr(t.device, "centre", None) else "N/A"
                dept_name = t.device.department.name if getattr(t.device, "department", None) else "N/A"

                ass_name = _assignee_name(t)
                ass_email = _assignee_email(t)

                device_period = Paragraph(
                    f"<b>{serial}</b><br/>{dname}<br/><font size='6.8' color='#666666'>{period_name}</font>",
                    styles["Cell"]
                )
                status_cell = Paragraph(
                    f"<b>{status}</b><br/>{completed}",
                    styles["Cell"]
                )
                centre_cell = Paragraph(
                    f"{centre_name}<br/><font size='6.8' color='#666666'>{dept_name}</font>",
                    styles["Cell"]
                )
                assignee_cell = Paragraph(
                    f"{ass_name}<br/><font size='6.6' color='#666666'>{ass_email}</font>",
                    styles["CellSmall"]
                )

                # ✅ Activities as tags (chips) + Notes below
                if getattr(t, "no_ppm_activity_performed", False):
                    reason = (getattr(t, "reason", "") or "").strip() or "N/A"
                    notes_cell = [
                        _no_activity_chip(),
                        Spacer(1, 3),
                        Paragraph(f"<b>Reason:</b> {reason}", styles["NoteText"]),
                    ]
                else:
                    activity_names = [a.name for a in t.activities.all()] if t.activities.exists() else []
                    notes = (getattr(t, "remarks", "") or "").strip() or "-"
                    chips = _build_activity_tag_grid(activity_names) if activity_names else None

                    flow = []
                    if chips:
                        flow.append(chips)
                        flow.append(Spacer(1, 3))
                    else:
                        flow.append(Paragraph("<font color='#6B7280'>No activities selected</font>", styles["NoteText"]))
                        flow.append(Spacer(1, 3))

                    flow.append(Paragraph(f"<b>Notes:</b> {notes}", styles["NoteText"]))
                    notes_cell = flow

                table_data.append([device_period, status_cell, centre_cell, assignee_cell, notes_cell])

            # ✅ DO NOT CHANGE your column sizes (kept exactly)
            table = Table(
                table_data,
                colWidths=[57 * mm, 32 * mm, 25 * mm, 40 * mm, 119 * mm],
                repeatRows=1,
            )
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#143C50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))

            elements.append(table)
            doc.build(elements)
            return response

        # ---------- EXCEL ----------
        if export_type == "excel":
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output, {"in_memory": True})
            ws = workbook.add_worksheet("PPM Report")

            header_fmt = workbook.add_format({"bold": True, "bg_color": "#143C50", "font_color": "white", "border": 1})
            cell_fmt = workbook.add_format({"border": 1, "valign": "top"})
            wrap_fmt = workbook.add_format({"border": 1, "valign": "top", "text_wrap": True})

            headers = [
                "Serial Number",
                "Device Name",
                "PPM Period",
                "Centre",
                "Department",
                "Assignee Name",
                "Assignee Email",
                "Status",
                "Completed Date",
                "Activities / Notes",
            ]
            for col, h in enumerate(headers):
                ws.write(0, col, h, header_fmt)

            row = 1
            for t in export_tasks:
                serial = getattr(t.device, "serial_number", "") or "N/A"
                dname = getattr(t.device, "device_name", "") or "N/A"
                period_name = t.period.name if t.period else "N/A"
                centre_name = t.device.centre.name if getattr(t.device, "centre", None) else "N/A"
                dept_name = t.device.department.name if getattr(t.device, "department", None) else "N/A"
                ass_name = _assignee_name(t)
                ass_email = _assignee_email(t)

                status = "Not Done" if getattr(t, "no_ppm_activity_performed", False) else ("Completed" if t.completed_date else "Open")
                completed = t.completed_date.strftime("%Y-%m-%d") if t.completed_date else "-"

                if getattr(t, "no_ppm_activity_performed", False):
                    activities_notes = f"Reason: {(getattr(t, 'reason', '') or '').strip() or 'N/A'}"
                else:
                    acts = ", ".join([a.name for a in t.activities.all()]) if t.activities.exists() else "None"
                    notes = (getattr(t, "remarks", "") or "").strip() or "-"
                    activities_notes = f"Acts: {acts}\nNotes: {notes}"

                ws.write(row, 0, serial, cell_fmt)
                ws.write(row, 1, dname, cell_fmt)
                ws.write(row, 2, period_name, cell_fmt)
                ws.write(row, 3, centre_name, cell_fmt)
                ws.write(row, 4, dept_name, cell_fmt)
                ws.write(row, 5, ass_name, cell_fmt)
                ws.write(row, 6, ass_email, cell_fmt)
                ws.write(row, 7, status, cell_fmt)
                ws.write(row, 8, completed, cell_fmt)
                ws.write(row, 9, activities_notes, wrap_fmt)
                row += 1

            ws.set_column(0, 0, 16)
            ws.set_column(1, 1, 26)
            ws.set_column(2, 2, 20)
            ws.set_column(3, 4, 18)
            ws.set_column(5, 6, 22)
            ws.set_column(7, 8, 14)
            ws.set_column(9, 9, 60)

            workbook.close()
            output.seek(0)

            response = HttpResponse(
                output.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            filename = f"PPM_Report_{current_period.name if current_period else 'All'}_{centre_obj.name if centre_obj else 'All'}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

    # Pagination
    tasks_query = tasks_query.order_by("-created_at", "id")
    from django.core.paginator import Paginator
    paginator = Paginator(tasks_query, items_per_page)
    try:
        tasks = paginator.page(page_number)
    except Exception:
        tasks = paginator.page(1)

    context = {
        "tasks": tasks,
        "periods": periods,
        "period_filter": period_filter,
        "current_period": current_period,
        "centres": centres,
        "centre_filter": centre_filter,
        "search_query": search_query,
        "items_per_page": items_per_page,
        "items_per_page_options": [10, 25, 50, 100, 500],
        "paginator": paginator,
        "approved_devices": approved_devices,
        "devices_with_ppm": devices_with_ppm,
        "devices_without_ppm": devices_without_ppm,
        "completed_on_time": completed_on_time,
        "overdue_tasks": overdue_tasks,
        "tasks_due_soon": tasks_due_soon,
        "ppm_completion_rate": ppm_completion_rate,
        "avg_completion_time": avg_completion_time,
        "ppm_status_labels": ppm_status_labels,
        "ppm_status_data": ppm_status_data,
        "ppm_status_colors": ppm_status_colors,
        "ppm_tasks_by_activity": ppm_tasks_by_activity,
        "ppm_by_centre": ppm_by_centre,
        "device_condition_breakdown": device_condition_breakdown,
        "recent_ppm_completions": recent_ppm_completions,
        "total_ppm_tasks": total_ppm_tasks,
        "tasks_done": tasks_done,
        "tasks_not_done": tasks_not_done,
        "view_name": "ppm_report",
    }
    return render(request, "ppm/ppm_report.html", context)



@login_required
@user_passes_test(is_superuser)
def manage_activities(request):
    activities = PPMActivity.objects.all()
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        PPMActivity.objects.create(name=name, description=description)
        messages.success(request, "Activity added successfully.")
        return redirect('manage_activities')
    context = {'activities': activities}
    return render(request, 'ppm/manage_activities.html', context)

@login_required
@user_passes_test(is_superuser)
def activity_edit(request, activity_id):
    activity = get_object_or_404(PPMActivity, id=activity_id)
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        activity.name = name
        activity.description = description
        activity.save()
        messages.success(request, "Activity updated successfully.")
        return redirect('manage_activities')
    context = {'activity': activity}
    return render(request, 'ppm/activity_edit.html', context)

@login_required
@user_passes_test(is_superuser)
@require_POST
def activity_delete(request, activity_id):
    activity = get_object_or_404(PPMActivity, id=activity_id)
    activity.delete()
    messages.success(request, "Activity deleted successfully.")
    return redirect('manage_activities')

@login_required
@user_passes_test(is_superuser)
def manage_periods(request):
    periods = PPMPeriod.objects.all()
    activities = PPMActivity.objects.all()
    if request.method == 'POST':
        name = request.POST.get('name')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'on'
        selected_activities = request.POST.getlist('activities')
        period = PPMPeriod.objects.create(
            name=name,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active
        )
        period.activities.set(selected_activities)
        messages.success(request, "Period added successfully.")
        return redirect('manage_periods')
    context = {'periods': periods, 'activities': activities}
    return render(request, 'ppm/manage_periods.html', context)

@login_required
@user_passes_test(is_superuser)
def period_edit(request, period_id):
    period = get_object_or_404(PPMPeriod, id=period_id)
    activities = PPMActivity.objects.all()
    if request.method == 'POST':
        name = request.POST.get('name')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'on'
        selected_activities = request.POST.getlist('activities')
        period.name = name
        period.start_date = start_date
        period.end_date = end_date
        period.is_active = is_active
        period.save()
        period.activities.set(selected_activities)
        messages.success(request, "Period updated successfully.")
        return redirect('manage_periods')
    context = {'period': period, 'activities': activities}
    return render(request, 'ppm/period_edit.html', context)

@login_required
@user_passes_test(is_superuser)
@require_POST
def period_delete(request, period_id):
    period = get_object_or_404(PPMPeriod, id=period_id)
    period.delete()
    messages.success(request, "Period deleted successfully.")
    return redirect('manage_periods')


