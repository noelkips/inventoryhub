from http.client import HTTPResponse
from venv import logger
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count, F, ExpressionWrapper, DurationField
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db import IntegrityError
from datetime import datetime, timedelta
from .models import PPMPeriod, PPMActivity, PPMTask
from devices.models import Import, Centre
import os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.units import mm
import xlsxwriter
from io import BytesIO
import random
import logging
from django.db.models import Q, Exists, OuterRef 


def is_superuser(user):
    return user.is_superuser

logger = logging.getLogger(__name__)




@user_passes_test(is_superuser)
def ppm_device_list(request):
    centres = Centre.objects.all()
    search_query = request.GET.get('search', '').strip()
    centre_filter = request.GET.get('centre', '')
    # NEW: Get the PPM status filter
    ppm_status_filter = request.GET.get('ppm_status', '') 
    
    try:
        items_per_page = int(request.GET.get('items_per_page', 10))
        if items_per_page not in [10, 25, 50, 100]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    active_period = PPMPeriod.objects.filter(is_active=True).first()
    
    if not active_period:
        devices = Import.objects.none()
        messages.warning(request, "No active PPM period. Please create and activate a period.")
    else:
        devices = Import.objects.all()

        # Efficiently annotate the QuerySet with PPM status (has_ppm_task)
        # This replaces the slower loop that was previously iterating over all devices
        ppm_task_exists = PPMTask.objects.filter(
            device=OuterRef('pk'), 
            period=active_period
        )
        devices = devices.annotate(
            has_ppm_task=Exists(ppm_task_exists)
        )
        
        # Apply Search and Centre Filters
        if search_query:
            devices = devices.filter(
                Q(serial_number__icontains=search_query) |
                Q(assignee_first_name__icontains=search_query) |
                Q(assignee_last_name__icontains=search_query) |
                Q(department__name__icontains=search_query)
            )
        if centre_filter and centre_filter != '':
            devices = devices.filter(centre_id=centre_filter)

        # NEW: Apply PPM Status Filter
        if ppm_status_filter == 'done':
            # Filter for devices where the PPM task exists (Done)
            devices = devices.filter(has_ppm_task=True)
        elif ppm_status_filter == 'not_done':
            # Filter for devices where the PPM task does not exist (Not Done)
            devices = devices.filter(has_ppm_task=False)

        # NOTE: The manual loop to set device.has_ppm_task is no longer needed here 
        # because the annotation ensures it's set on the resulting objects.

    paginator = Paginator(devices, items_per_page)
    page_number = request.GET.get('page', 1)
    try:
        devices = paginator.page(page_number)
    except:
        devices = paginator.page(1)

    activities = active_period.activities.all() if active_period else []

    # Custom page range for pagination (current page ± 2, first, last)
    page_range = []
    if paginator.num_pages > 1:
        start = max(1, devices.number - 2)
        end = min(paginator.num_pages + 1, devices.number + 3)
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
        'search_query': search_query,
        'centre_filter': centre_filter,
        'ppm_status_filter': ppm_status_filter, # NEW: Add the filter to report_data
        'items_per_page': items_per_page,
        'total_records': paginator.count,
    }

    context = {
        'devices': devices,
        'report_data': report_data,
        'centres': centres,
        'activities': activities,
        'active_period': active_period,
        'items_per_page_options': [10, 25, 50, 100],
        'page_range': page_range,
        'view_name': 'ppm_device_list',
    }
    return render(request, 'ppm/ppm_device_list.html', context)


@user_passes_test(is_superuser)
def ppm_task_create(request, device_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=400)

    try:
        device = get_object_or_404(Import, id=device_id)
        active_period = PPMPeriod.objects.filter(is_active=True).first()
        if not active_period:
            return JsonResponse({'success': False, 'error': 'No active PPM period.'}, status=400)

        activities_ids = request.POST.getlist('activities')
        if not activities_ids:
            return JsonResponse({'success': False, 'error': 'At least one activity must be selected.'}, status=400)

        # Validate activity IDs
        try:
            activities_ids = [int(id) for id in activities_ids]
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid activity IDs.'}, status=400)

        # Check if all activity IDs exist
        valid_activities = PPMActivity.objects.filter(id__in=activities_ids).count()
        if valid_activities != len(activities_ids):
            return JsonResponse({'success': False, 'error': 'One or more selected activities do not exist.'}, status=400)

        completed_date = request.POST.get('completed_date')
        if completed_date:
            try:
                completed_date = datetime.strptime(completed_date, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)
        else:
            completed_date = None

        remarks = request.POST.get('remarks', '')

        existing_task = PPMTask.objects.filter(device=device, period=active_period).first()
        is_new = False

        try:
            if existing_task:
                # Update existing task
                existing_task.activities.set(activities_ids)
                existing_task.completed_date = completed_date
                existing_task.remarks = remarks
                existing_task.updated_at = timezone.now()
                existing_task.save()
            else:
                # Create new task
                ppm_task = PPMTask.objects.create(
                    device=device,
                    period=active_period,
                    created_by=request.user,
                    completed_date=completed_date,
                    remarks=remarks
                )
                ppm_task.activities.set(activities_ids)
                is_new = True

            messages.success(request, f'PPM task {"created" if is_new else "updated"} successfully for {device.serial_number}!')
            return JsonResponse({
                'success': True,
                'message': f'PPM task {"created" if is_new else "updated"} successfully for {device.serial_number}!',
                'is_new': is_new,
                'device_name': device.serial_number
            })

        except IntegrityError as e:
            return JsonResponse({'success': False, 'error': f'Database error: {str(e)}'}, status=400)

    except Exception as e:
        # Log the error for debugging (use logging in production)
        print(f"Error in ppm_task_create: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An unexpected error occurred.'}, status=500)

@user_passes_test(is_superuser)
def get_ppm_task(request, device_id):
    try:
        # Fetch the device
        device = get_object_or_404(Import, id=device_id)
        active_period = PPMPeriod.objects.filter(is_active=True).first()
        if not active_period:
            return JsonResponse({'error': 'No active PPM period.'}, status=400)

        # Initialize response data with hardware details
        data = {
            'hardware': device.hardware or '',
            'system_model': device.system_model or '',
            'processor': device.processor or '',
            'ram_gb': device.ram_gb or '',
            'hdd_gb': device.hdd_gb or '',
        }

        # Fetch PPMTask if it exists
        task = PPMTask.objects.filter(device_id=device_id, period=active_period).first()
        if task:
            data.update({
                'activities': list(task.activities.values_list('id', flat=True)),
                'completed_date': task.completed_date.strftime('%Y-%m-%d') if task.completed_date else '',
                'remarks': task.remarks or '',
            })

        return JsonResponse(data)
    except Exception as e:
        print(f"Error in get_ppm_task: {str(e)}")
        return JsonResponse({'error': 'An unexpected error occurred.'}, status=500)
        
@login_required
def ppm_history(request, device_id=None):
    if request.user.is_superuser:
        tasks = PPMTask.objects.all()
    else:
        tasks = PPMTask.objects.filter(device__centre=request.user.centre) if request.user.centre else PPMTask.objects.none()

    if device_id:
        tasks = tasks.filter(device__id=device_id)

    # Search and filter
    search_query = request.GET.get('search', '').strip()
    centre_filter = request.GET.get('centre', '')
    if search_query:
        query = Q()
        for field in ['device__serial_number', 'device__assignee_first_name', 'device__assignee_last_name', 'device__department__name']:
            query |= Q(**{f'{field}__icontains': search_query}) & ~Q(**{f'{field}__isnull': True}) & ~Q(**{f'{field}': ''})
        tasks = tasks.filter(query)
    if centre_filter:
        tasks = tasks.filter(device__centre__id=centre_filter)

    # Pagination
    try:
        items_per_page = int(request.GET.get('items_per_page', 10))
        if items_per_page not in [10, 25, 50, 100]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    paginator = Paginator(tasks, items_per_page)
    page_number = request.GET.get('page', 1)
    try:
        tasks_on_page = paginator.page(page_number)
    except:
        tasks_on_page = paginator.page(1)

    centres = Centre.objects.all() if request.user.is_superuser else Centre.objects.filter(id=request.user.centre.id) if request.user.centre else Centre.objects.none()

    # Custom page range for pagination (current page ± 2, first, last)
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
        'total_records': tasks.count(),
        'search_query': search_query,
        'items_per_page': items_per_page,
        'centre_filter': centre_filter
    }

    context = {
        'tasks': tasks_on_page,
        'device_id': device_id,
        'centres': centres,
        'items_per_page_options': [10, 25, 50, 100],
        'report_data': report_data,
        'page_range': page_range,
        'view_name': 'ppm_history',  # For URL in template
    }
    return render(request, 'ppm/ppm_history.html', context)


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


@login_required
def ppm_report(request):
    # Determine user permissions and base query
    if request.user.is_superuser:
        centres = Centre.objects.all()
        device_query = Import.objects.all()
        base_tasks_query = PPMTask.objects.select_related(
            'device', 'device__centre', 'device__department', 'period', 'created_by'
        ).prefetch_related('activities')
    elif request.user.centre:
        centres = Centre.objects.filter(id=request.user.centre.id)
        device_query = Import.objects.filter(centre=request.user.centre)
        base_tasks_query = PPMTask.objects.filter(
            device__centre=request.user.centre
        ).select_related(
            'device', 'device__centre', 'device__department', 'period', 'created_by'
        ).prefetch_related('activities')
    else:
        centres = Centre.objects.none()
        device_query = Import.objects.none()
        base_tasks_query = PPMTask.objects.none()

    # Get all periods for filter
    periods = PPMPeriod.objects.all().order_by('-start_date')

    # Get filters
    period_filter = request.GET.get('period', '')
    centre_filter = request.GET.get('centre', '')
    search_query = request.GET.get('search', '').strip()
    items_per_page = request.GET.get('items_per_page', '10')
    page_number = request.GET.get('page', '1')
    export_type = request.GET.get('export', '')

    # Default to active period if no period selected
    current_period = None
    if not period_filter:
        active_period = PPMPeriod.objects.filter(is_active=True).first()
        if active_period:
            period_filter = str(active_period.id)
        else:
            latest_period = PPMPeriod.objects.order_by('-end_date').first()
            if latest_period:
                period_filter = str(latest_period.id)

    if period_filter:
        try:
            current_period = PPMPeriod.objects.get(id=period_filter)
        except PPMPeriod.DoesNotExist:
            messages.error(request, "Invalid period selected.")
            return redirect('ppm_report')

    # Validate items_per_page
    try:
        items_per_page = int(items_per_page)
        if items_per_page not in [10, 25, 50, 100, 500]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    # Validate page_number
    try:
        page_number = int(page_number) if page_number else 1
    except ValueError:
        page_number = 1

    # Apply centre filter to device_query if applicable
    if centre_filter and (request.user.is_superuser or str(request.user.centre.id) == centre_filter):
        device_query = device_query.filter(centre__id=centre_filter)

    approved_devices = device_query.filter(is_approved=True, is_disposed=False).count()

    # PPM stats device-based for the selected period
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
    total_ppm_tasks = 0

    if current_period:
        tasks_query = base_tasks_query.filter(period=current_period).select_related(
            'device', 'device__centre', 'device__department', 'period', 'created_by'
        ).prefetch_related('activities')

        # Apply centre filter to tasks if applicable
        if centre_filter and (request.user.is_superuser or str(request.user.centre.id) == centre_filter):
            tasks_query = tasks_query.filter(device__centre__id=centre_filter)

        # Search filter on tasks
        if search_query:
            query = (
                Q(device__serial_number__icontains=search_query) |
                Q(device__assignee_first_name__icontains=search_query) |
                Q(device__assignee_last_name__icontains=search_query) |
                Q(device__department__name__icontains=search_query) |
                Q(remarks__icontains=search_query) |
                Q(device__hardware__icontains=search_query)
            )
            tasks_query = tasks_query.filter(query)

        total_ppm_tasks = tasks_query.count()
        devices_with_ppm = tasks_query.values('device').distinct().count()
        devices_without_ppm = approved_devices - devices_with_ppm
        ppm_completion_rate = round((devices_with_ppm / approved_devices * 100) if approved_devices > 0 else 0, 1)

        now = timezone.now().date()
        is_past_period = current_period.end_date < now
        overdue_tasks = devices_without_ppm if is_past_period else 0

        seven_days_ahead = now + timedelta(days=7)
        if current_period.end_date <= seven_days_ahead and current_period.end_date >= now:
            tasks_due_soon = devices_without_ppm

        completed_on_time = tasks_query.filter(completed_date__lte=current_period.end_date, completed_date__isnull=False).values('device').distinct().count()

        # Average completion time for completed PPMs
        completed_with_time = tasks_query.filter(
            completed_date__isnull=False
        ).annotate(
            days_to_complete=ExpressionWrapper(F('completed_date') - F('period__start_date'), output_field=DurationField())
        )
        if completed_with_time.exists():
            total_days = sum(task.days_to_complete.days for task in completed_with_time if task.days_to_complete)
            avg_completion_time = round(total_days / completed_with_time.count(), 1)

        if not is_past_period:
            ppm_status_labels = ['PPM Done', 'PPM Not Done']
            ppm_status_data = [devices_with_ppm, devices_without_ppm]
            ppm_status_colors = ['#10B981', '#F59E0B']
        else:
            ppm_status_labels = ['PPM Done', 'PPM Overdue']
            ppm_status_data = [devices_with_ppm, devices_without_ppm]
            ppm_status_colors = ['#10B981', '#EF4444']

        ppm_tasks_by_activity = tasks_query.values('activities__name').annotate(
            count=Count('id')
        ).order_by('-count') if tasks_query.exists() else []

    # PPM by centre device-based
    centres_to_show = centres if not centre_filter else centres.filter(id=centre_filter)
    ppm_by_centre = []
    for centre in centres_to_show:
        centre_device_query = device_query.filter(centre=centre)
        centre_approved = centre_device_query.filter(is_approved=True, is_disposed=False).count()
        centre_with_ppm = base_tasks_query.filter(period=current_period, device__centre=centre).values('device').distinct().count()
        if centre_approved > 0:
            ppm_by_centre.append({
                'device__centre__name': centre.name,
                'total': centre_approved,
                'completed': centre_with_ppm
            })
    ppm_by_centre = sorted(ppm_by_centre, key=lambda x: x.get('completed', 0), reverse=True)

    # Device condition breakdown from all eligible devices
    device_condition_breakdown = device_query.filter(is_approved=True, is_disposed=False).values(
        'device_condition'
    ).annotate(count=Count('id')).order_by('-count')

    # Recent completions
    recent_ppm_completions = tasks_query.filter(
        completed_date__isnull=False
    ).order_by('-completed_date')[:10]

    # Handle exports
    if export_type in ['pdf', 'excel']:
        export_tasks = list(tasks_query)
        if approved_devices == 0:
            messages.error(request, "No data available for the selected filters.")
            return redirect('ppm_report')

        centre = centres.get(id=centre_filter) if centre_filter else None

        if export_type == 'pdf':
            response = HttpResponse(content_type='application/pdf')
            filename = f"PPM_Report_{current_period.name if current_period else 'All'}_{centre.name if centre else 'All'}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

            doc = SimpleDocTemplate(
                response,
                pagesize=landscape(A4),
                rightMargin=10*mm,
                leftMargin=10*mm,
                topMargin=15*mm,
                bottomMargin=15*mm
            )

            elements = []
            styles = getSampleStyleSheet()

            styles.add(ParagraphStyle(
                name='ReportTitle',
                fontSize=18,
                leading=22,
                textColor=colors.HexColor('#143C50'),
                alignment=1,  # TA_CENTER
                spaceAfter=6
            ))
            styles.add(ParagraphStyle(
                name='SubTitle',
                fontSize=12,
                leading=14,
                textColor=colors.HexColor('#143C50'),
                alignment=1,  # TA_CENTER
                spaceAfter=12
            ))
            styles.add(ParagraphStyle(
                name='Cell',
                fontSize=8,
                leading=10,
                wordWrap='CJK'
            ))

            # Title
            elements.append(Paragraph('MOHI IT - PPM REPORT', styles['ReportTitle']))
            if current_period:
                elements.append(Paragraph(f'Period: {current_period.name} ({current_period.start_date} to {current_period.end_date})', styles['SubTitle']))
            elements.append(Paragraph(
                f'Generated: {timezone.now().strftime("%B %d, %Y at %I:%M %p")}',
                styles['SubTitle']
            ))
            if centre:
                elements.append(Paragraph(f'Centre: {centre.name}', styles['SubTitle']))
            elements.append(Spacer(1, 12))

            # Statistics Summary
            stats_data = [
                ['Metric', 'Value'],
                ['Total Devices', str(approved_devices)],
                ['Completed PPM', str(devices_with_ppm)],
                ['Incomplete PPM', str(devices_without_ppm)],
                ['Overdue PPM', str(overdue_tasks)],
                ['Completion Rate', f'{ppm_completion_rate}%'],
            ]

            stats_table = Table(stats_data, colWidths=[80*mm, 40*mm])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#143C50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(stats_table)
            elements.append(Spacer(1, 12))

            # Tasks table
            table_data = [[
                'No.',
                'Serial Number',
                'Hardware',
                'Centre',
                'Department',
                'Assignee',
                'Activities',
                'Status',
                'Completed Date',
                'Remarks'
            ]]

            for idx, task in enumerate(export_tasks, 1):
                activities_str = ', '.join(task.activities.values_list('name', flat=True)[:3])
                if task.activities.count() > 3:
                    activities_str += '...'

                table_data.append([
                    str(idx),
                    Paragraph(task.device.serial_number or 'N/A', styles['Cell']),
                    Paragraph(task.device.hardware or 'N/A', styles['Cell']),
                    Paragraph(task.device.centre.name if task.device.centre else 'N/A', styles['Cell']),
                    Paragraph(task.device.department.name if task.device.department else 'N/A', styles['Cell']),
                    Paragraph(f"{task.device.assignee_first_name or ''} {task.device.assignee_last_name or ''}".strip() or 'N/A', styles['Cell']),
                    Paragraph(activities_str or 'N/A', styles['Cell']),
                    'Completed' if task.completed_date else 'Incomplete',
                    task.completed_date.strftime('%Y-%m-%d') if task.completed_date else 'N/A',
                    Paragraph((task.remarks or 'N/A')[:50], styles['Cell'])
                ])

            tasks_table = Table(table_data, colWidths=[
                10*mm, 25*mm, 25*mm, 25*mm, 25*mm, 25*mm, 35*mm, 15*mm, 22*mm, 35*mm
            ])

            tasks_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#288CC8')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
            ]))

            elements.append(Paragraph('<b>DETAILED TASK LIST</b>', styles['SubTitle']))
            elements.append(tasks_table)

            # Watermark
            def add_watermark(canvas, doc):
                canvas.saveState()
                canvas.setFont("Helvetica", 60)
                canvas.setFillGray(0.9, 0.15)
                canvas.rotate(45)
                canvas.drawCentredString(400, 100, "MOHI IT")
                canvas.restoreState()

            doc.build(elements, onFirstPage=add_watermark, onLaterPages=add_watermark)
            return response

        if export_type == 'excel':
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet('PPM Report')

            # Formats
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#143C50',
                'font_color': 'white',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1
            })

            cell_format = workbook.add_format({
                'align': 'left',
                'valign': 'top',
                'border': 1,
                'text_wrap': True
            })

            date_format = workbook.add_format({
                'align': 'left',
                'border': 1,
                'num_format': 'yyyy-mm-dd'
            })

            # Write period info
            if current_period:
                worksheet.write(0, 0, f'Period: {current_period.name}', header_format)
                worksheet.write(1, 0, f'Start: {current_period.start_date}', cell_format)
                worksheet.write(2, 0, f'End: {current_period.end_date}', cell_format)
                start_row = 4
            else:
                start_row = 0

            # Write headers
            headers = [
                'No.', 'Serial Number', 'Hardware', 'Centre', 'Department',
                'Assignee First Name', 'Assignee Last Name', 'Assignee Email',
                'Activities', 'Status', 'Completed Date', 'Remarks', 'Period',
                'Created By', 'Created At'
            ]

            for col, header in enumerate(headers):
                worksheet.write(start_row, col, header, header_format)

            # Write data
            for row, task in enumerate(export_tasks, start_row + 1):
                activities = ', '.join(task.activities.values_list('name', flat=True))

                worksheet.write(row, 0, row - start_row, cell_format)
                worksheet.write(row, 1, task.device.serial_number or 'N/A', cell_format)
                worksheet.write(row, 2, task.device.hardware or 'N/A', cell_format)
                worksheet.write(row, 3, task.device.centre.name if task.device.centre else 'N/A', cell_format)
                worksheet.write(row, 4, task.device.department.name if task.device.department else 'N/A', cell_format)
                worksheet.write(row, 5, task.device.assignee_first_name or 'N/A', cell_format)
                worksheet.write(row, 6, task.device.assignee_last_name or '', cell_format)
                worksheet.write(row, 7, task.device.assignee_email_address or 'N/A', cell_format)
                worksheet.write(row, 8, activities or 'N/A', cell_format)
                worksheet.write(row, 9, 'Completed' if task.completed_date else 'Incomplete', cell_format)

                if task.completed_date:
                    worksheet.write(row, 10, task.completed_date, date_format)
                else:
                    worksheet.write(row, 10, 'N/A', cell_format)

                worksheet.write(row, 11, task.remarks or 'N/A', cell_format)
                worksheet.write(row, 12, task.period.name if task.period else 'N/A', cell_format)
                worksheet.write(row, 13, task.created_by.username if task.created_by else 'N/A', cell_format)
                worksheet.write(row, 14, task.created_at.strftime('%Y-%m-%d %H:%M') if task.created_at else 'N/A', cell_format)

            # Set column widths
            worksheet.set_column('A:A', 8)
            worksheet.set_column('B:C', 20)
            worksheet.set_column('D:E', 25)
            worksheet.set_column('F:H', 20)
            worksheet.set_column('I:I', 40)
            worksheet.set_column('J:K', 15)
            worksheet.set_column('L:L', 35)
            worksheet.set_column('M:O', 20)

            workbook.close()
            output.seek(0)

            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            filename = f"PPM_Report_{current_period.name if current_period else 'All'}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

    # Pagination for display
    tasks_query = tasks_query.order_by('-created_at', 'id')
    paginator = Paginator(tasks_query, items_per_page)
    try:
        tasks = paginator.page(page_number)
    except:
        tasks = paginator.page(1)

    context = {
        'tasks': tasks,
        'periods': periods,
        'period_filter': period_filter,
        'current_period': current_period,
        'centres': centres,
        'centre_filter': centre_filter,
        'search_query': search_query,
        'items_per_page': items_per_page,
        'items_per_page_options': [10, 25, 50, 100, 500],
        'paginator': paginator,
        'approved_devices': approved_devices,
        'devices_with_ppm': devices_with_ppm,
        'devices_without_ppm': devices_without_ppm,
        'completed_on_time': completed_on_time,
        'overdue_tasks': overdue_tasks,
        'tasks_due_soon': tasks_due_soon,
        'ppm_completion_rate': ppm_completion_rate,
        'avg_completion_time': avg_completion_time,
        'ppm_status_labels': ppm_status_labels,
        'ppm_status_data': ppm_status_data,
        'ppm_status_colors': ppm_status_colors,
        'ppm_tasks_by_activity': ppm_tasks_by_activity,
        'ppm_by_centre': ppm_by_centre,
        'device_condition_breakdown': device_condition_breakdown,
        'recent_ppm_completions': recent_ppm_completions,
        'view_name': 'ppm_report',
    }

    return render(request, 'ppm/ppm_report.html', context)