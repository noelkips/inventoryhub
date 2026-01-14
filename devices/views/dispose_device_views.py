# dispose_device_views.py
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
from io import TextIOWrapper
import csv
import logging
from django.http import HttpResponse
from django.contrib.contenttypes.models import ContentType

from devices.models import Import, Centre, Department, CustomUser, Notification

logger = logging.getLogger(__name__)

@login_required
def dispose_add(request):
    if request.method == 'POST':
        if 'file' in request.FILES:
            return handle_dispose_bulk_upload(request)
        else:
            return handle_dispose_single(request)

    context = {}
    return render(request, 'import/disposed/dispose_add.html', context)


def handle_dispose_single(request):
    try:
        with transaction.atomic():
            serial_number = request.POST.get('serial_number', '').strip()
            hardware = request.POST.get('hardware', '').strip()
            disposal_reason = request.POST.get('disposal_reason', '').strip()

            if not all([serial_number, hardware, disposal_reason]):
                messages.error(request, "Serial Number, Hardware, and Disposal Reason are required.")
                return redirect('dispose_add')

            # BLOCK IF ALREADY EXISTS
            if Import.objects.filter(serial_number=serial_number).exists():
                messages.error(request, f"Device with serial {serial_number} already exists. Use normal disposal workflow.")
                return redirect('dispose_add')

            device = Import(
                added_by=request.user,
                serial_number=serial_number,
                hardware=hardware,
                disposal_reason=disposal_reason,
                is_disposed=True,
                is_approved=not request.user.is_trainer,
                approved_by=request.user if not request.user.is_trainer else None,
                date=timezone.now().date(),

                # Optional fields
                system_model=request.POST.get('system_model'),
                processor=request.POST.get('processor'),
                ram_gb=request.POST.get('ram_gb'),
                hdd_gb=request.POST.get('hdd_gb'),
                assignee_first_name=request.POST.get('assignee_first_name'),
                assignee_last_name=request.POST.get('assignee_last_name'),
                assignee_email_address=request.POST.get('assignee_email_address'),
                device_condition=request.POST.get('device_condition'),
                status=request.POST.get('status'),
            )
            device.save()

            if request.user.is_trainer:
                admins = CustomUser.objects.filter(is_superuser=True)
                for admin in admins:
                    Notification.objects.create(
                        user=admin,
                        message=f"Trainer {request.user.username} disposed new device: {serial_number} ({hardware})",
                        content_type=ContentType.objects.get_for_model(Import),
                        object_id=device.pk
                    )

            status = "(pending approval)" if request.user.is_trainer else ""
            messages.success(request, f"Device {serial_number} disposed{status}.")
            return redirect('display_disposed_imports')

    except Exception as e:
        logger.error(f"Single disposal error: {e}", exc_info=True)
        messages.error(request, "Error disposing device.")
        return redirect('dispose_add')


def handle_dispose_bulk_upload(request):
    file = request.FILES['file']
    if not file.name.lower().endswith('.csv'):
        messages.error(request, "Only CSV files allowed.")
        return redirect('dispose_add')

    try:
        decoded_file = TextIOWrapper(file.file, encoding='utf-8-sig')
        reader = csv.reader(decoded_file)
        headers = next(reader, None)
        if not headers:
            messages.error(request, "CSV is empty.")
            return redirect('dispose_add')

        headers = [h.lower().strip() for h in headers]
        required = ['serial_number', 'hardware', 'disposal_reason']
        missing = [col for col in required if col not in headers]
        if missing:
            messages.error(request, f"Missing required columns: {', '.join(missing)}")
            return redirect('dispose_add')

        stats = {'created': 0, 'skipped_existing': 0, 'skipped_validation': 0}
        devices = []
        admins = CustomUser.objects.filter(is_superuser=True)

        for row in reader:
            if not any(row):
                continue
            row_dict = dict(zip(headers, [cell.strip() for cell in row]))
            sn = row_dict.get('serial_number')
            hw = row_dict.get('hardware')
            reason = row_dict.get('disposal_reason') or "No reason provided"

            if not all([sn, hw]):
                stats['skipped_validation'] += 1
                continue

            if Import.objects.filter(serial_number=sn).exists():
                stats['skipped_existing'] += 1
                continue

            device = Import(
                added_by=request.user,
                serial_number=sn,
                hardware=hw,
                disposal_reason=reason,
                is_disposed=True,
                is_approved=not request.user.is_trainer,
                approved_by=request.user if not request.user.is_trainer else None,
                date=timezone.now().date(),

                system_model=row_dict.get('system_model'),
                processor=row_dict.get('processor'),
                ram_gb=row_dict.get('ram_gb'),
                hdd_gb=row_dict.get('hdd_gb'),
                assignee_first_name=row_dict.get('assignee_first_name'),
                assignee_last_name=row_dict.get('assignee_last_name'),
                assignee_email_address=row_dict.get('assignee_email_address'),
                device_condition=row_dict.get('device_condition'),
                status=row_dict.get('status'),
            )
            devices.append(device)
            stats['created'] += 1

        if devices:
            Import.objects.bulk_create(devices)

            if request.user.is_trainer:
                for device in devices:
                    for admin in admins:
                        Notification.objects.create(
                            user=admin,
                            message=f"Trainer {request.user.username} disposed: {device.serial_number} ({device.hardware})",
                            content_type=ContentType.objects.get_for_model(Import),
                            object_id=device.pk
                        )

        msg = f"Disposed {stats['created']} new devices"
        if stats['skipped_existing']: msg += f", {stats['skipped_existing']} already exist"
        if stats['skipped_validation']: msg += f", {stats['skipped_validation']} invalid"
        if request.user.is_trainer: msg += " (pending approval)"
        messages.success(request, msg)

    except Exception as e:
        logger.error(f"Bulk dispose error: {e}")
        messages.error(request, f"Error processing file: {e}")

    return redirect('display_disposed_imports')


def download_dispose_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="dispose_template.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'serial_number', 'hardware', 'disposal_reason',
        'system_model', 'processor', 'ram_gb', 'hdd_gb',
        'assignee_first_name', 'assignee_last_name', 'assignee_email_address',
        'device_condition', 'status'
    ])
    writer.writerow([
        'SN123456', 'Dell Latitude 5400', 'Stolen', 'Latitude 5400', 'i5-8265U', '8', '256',
        'John', 'Doe', 'john@example.com', 'Damaged', 'Stolen'
    ])
    return response