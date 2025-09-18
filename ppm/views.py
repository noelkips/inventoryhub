from http.client import HTTPResponse
from venv import logger
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db import IntegrityError
from datetime import datetime
from .models import PPMPeriod, PPMActivity, PPMTask
from devices.models import Import, Centre

def is_superuser(user):
    return user.is_superuser


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db import IntegrityError
from datetime import datetime
from .models import PPMPeriod, PPMActivity, PPMTask
from devices.models import Import, Centre

def is_superuser(user):
    return user.is_superuser

@user_passes_test(is_superuser)
def ppm_device_list(request):
    centres = Centre.objects.all()
    search_query = request.GET.get('search', '').strip()
    centre_filter = request.GET.get('centre', '')
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
        if search_query:
            devices = devices.filter(
                Q(serial_number__icontains=search_query) |
                Q(assignee_first_name__icontains=search_query) |
                Q(assignee_last_name__icontains=search_query) |
                Q(department__name__icontains=search_query)
            )
        if centre_filter and centre_filter != '':
            devices = devices.filter(centre_id=centre_filter)

        # Check for existing PPM tasks in the active period
        for device in devices:
            device.has_ppm_task = PPMTask.objects.filter(device=device, period=active_period).exists()

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
        'view_name': 'ppm_device_list',  # For URL in template
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


import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import Q, Count
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.graphics.shapes import String
from reportlab.pdfgen import canvas
import random
from .models import PPMPeriod, PPMActivity, PPMTask
from devices.models import Import, Centre
import logging

logger = logging.getLogger(__name__)

@login_required
def ppm_report(request):
    centres = Centre.objects.all() if request.user.is_superuser else Centre.objects.filter(id=request.user.centre.id) if request.user.centre else Centre.objects.none()
    centre_filter = request.GET.get('centre', '')
    search_query = request.GET.get('search', '').strip()
    items_per_page = request.GET.get('items_per_page', '10')
    scope = request.GET.get('scope', 'page')
    page_number = request.GET.get('page', '1')

    # Convert and validate items_per_page
    try:
        items_per_page = int(items_per_page)
        if items_per_page not in [10, 25, 50, 100, 500]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    # Convert and validate page_number
    try:
        page_number = int(page_number) if page_number else 1
    except ValueError:
        page_number = 1

    # Filter tasks based on user permissions with proper select_related and ordering
    tasks = PPMTask.objects.select_related('device', 'period', 'created_by').prefetch_related('activities').order_by('id')
    if not request.user.is_superuser and request.user.centre:
        tasks = tasks.filter(device__centre=request.user.centre)

    # Apply centre filter
    if centre_filter and (request.user.is_superuser or str(request.user.centre.id) == centre_filter):
        tasks = tasks.filter(device__centre__id=centre_filter)

    # Apply search filter
    if search_query:
        query = (
            Q(device__serial_number__icontains=search_query) |
            Q(device__assignee_first_name__icontains=search_query) |
            Q(device__assignee_last_name__icontains=search_query) |
            Q(device__department__name__icontains=search_query) |
            Q(remarks__icontains=search_query) |
            Q(period__name__icontains=search_query)
        )
        tasks = tasks.filter(query)

    # PPM statistics
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(completed_date__isnull=False).count()
    overdue_tasks = tasks.filter(period__end_date__lt=timezone.now().date(), completed_date__isnull=True).count()
    tasks_by_status = {
        'Completed': completed_tasks,
        'Incomplete': total_tasks - completed_tasks
    }
    tasks_by_activity = tasks.values('activities__name').annotate(count=Count('id')).order_by('-count')

    # Pagination
    if scope == 'page':
        paginator = Paginator(tasks, items_per_page)
        try:
            tasks = paginator.page(page_number)
        except:
            tasks = paginator.page(1)
    else:
        tasks = tasks[:500]  # Limit to 500 for performance in 'all' scope

    # Handle PDF export - Force center selection
    if request.GET.get('export') == 'pdf':
        if not centre_filter:
            messages.error(request, "Please select a centre to generate the report.")
            return redirect('ppm_report')
        try:
            # Ensure the center is valid for the user
            centre = Centre.objects.get(id=centre_filter)
            if not request.user.is_superuser and str(request.user.centre.id) != centre_filter:
                messages.error(request, "You can only generate a report for your assigned centre.")
                return redirect('ppm_report')
        except Centre.DoesNotExist:
            messages.error(request, "Invalid centre selected.")
            return redirect('ppm_report')

        try:
            # Debug: Check if tasks is empty
            if not tasks:
                messages.error(request, "No tasks available for the selected centre.")
                return redirect('ppm_report')

            # Setup PDF response
            response = HttpResponse(content_type='application/pdf')
            filename = f"PPM_Report_{'All' if scope == 'all' else 'Page'}_{datetime.now().strftime('%Y%m%d')}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

            # Initialize PDF document
            doc = SimpleDocTemplate(response, pagesize=(A4[1], A4[0]), rightMargin=10*mm, leftMargin=10*mm, topMargin=15*mm, bottomMargin=15*mm)
            elements = []
            styles = getSampleStyleSheet()
            styles.add(ParagraphStyle(name='ReportTitle', fontSize=18, leading=22, textColor=colors.black, alignment=1))
            styles.add(ParagraphStyle(name='SubTitle', fontSize=14, leading=18, textColor=colors.black, alignment=1))
            styles.add(ParagraphStyle(name='CustomBody', fontSize=12, leading=14))
            styles.add(ParagraphStyle(name='Cell', parent=styles['Normal'], fontSize=10, leading=12, alignment=TA_LEFT, wordWrap='CJK'))
            styles.add(ParagraphStyle(name='DeviceInfo', parent=styles['Cell'], leading=10))
            styles.add(ParagraphStyle(name='Remarks', parent=styles['Cell'], wordWrap='CJK'))

            # Add title and generation info
            elements.append(Paragraph('MOHO IT PPM Report', styles['ReportTitle']))
            elements.append(Paragraph(f'Generated on {timezone.now().strftime("%I:%M %p EAT, %A, %B %d, %Y")}', styles['SubTitle']))
            elements.append(Paragraph(f'Centre: {centre.name}', styles['SubTitle']))
            elements.append(Spacer(1, 12))

            # Summary Statistics Table
            stats_data = [
                ['Statistic', 'Value'],
                ['Total PPM Tasks', str(total_tasks)],
                ['Completed Tasks', str(completed_tasks)],
                ['Overdue Tasks', str(overdue_tasks)],
                ['Tasks by Status', f'Completed: {tasks_by_status["Completed"]}, Incomplete: {tasks_by_status["Incomplete"]}'],
            ]
            for item in tasks_by_activity:
                stats_data.append([f'Tasks by Activity: {item["activities__name"] or "N/A"}', str(item['count'])])
            stats_table = Table(stats_data, colWidths=[80*mm, 60*mm])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            elements.append(stats_table)
            elements.append(Spacer(1, 12))

            # TASKS DONE Table
            data_tasks = [['No.', 'Device Details', 'Tasks Done', 'Date', 'Remarks']]
            for idx, task in enumerate(tasks.object_list if hasattr(tasks, 'object_list') else tasks, 1):
                device_details = f"{task.device.serial_number or 'N/A'}<br/>{task.device.hardware or 'N/A'}<br/><b>Department:</b> {task.device.department.name if task.device.department else 'N/A'}<br/><b>Assignee:</b> {task.device.assignee_first_name or 'N/A'} {task.device.assignee_last_name or ''}"
                tasks_done = ', '.join(task.activities.values_list('name', flat=True)) or 'N/A'
                date = task.completed_date.strftime('%Y-%m-%d') if task.completed_date else 'N/A'
                data_tasks.append([str(idx), Paragraph(device_details, styles['DeviceInfo']), Paragraph(tasks_done, styles['Cell']), date, Paragraph(task.remarks or 'N/A', styles['Remarks'])])
            if not tasks:
                data_tasks.append(['', 'No tasks available for this centre.', '', '', ''])
            table_tasks = Table(data_tasks, colWidths=[20*mm, 80*mm, 100*mm, 40*mm, 40*mm])
            table_tasks.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            elements.append(Paragraph("<b>TASKS DONE</b>", styles['SubTitle']))
            elements.append(table_tasks)

            # Watermark function with period scattered across the page
            def add_watermark(canvas, doc):
                period_name = tasks.object_list[0].period.name if tasks.object_list else 'N/A'
                watermark_text = f"{period_name}"
                canvas.saveState()
                canvas.setFont("Helvetica", 10)  # Larger font
                canvas.setFillGray(0.8, 0.8)  # Light gray
                # Generate 20 random positions to scatter the watermark
                for _ in range(20):
                    x = random.randint(10, int(doc.pagesize[0] - 10))  # Random x within page width
                    y = random.randint(10, int(doc.pagesize[1] - 10))  # Random y within page height
                    canvas.drawString(x, y, watermark_text)  # Scattered placement
                canvas.restoreState()

            doc.build(elements, onFirstPage=add_watermark, onLaterPages=add_watermark)

        except Exception as e:
            logger.error(f"PDF generation failed: {str(e)}")
            return HttpResponse(f"Error generating PDF: {str(e)}", status=500)

        return response

    # Custom page range for pagination
    paginator = Paginator(tasks, items_per_page)
    page_range = []
    if paginator.num_pages > 1:
        start = max(1, tasks.number - 2) if scope == 'page' else 1
        end = min(paginator.num_pages + 1, tasks.number + 3) if scope == 'page' else paginator.num_pages + 1
        page_range = list(range(start, end))
        if start > 2:
            page_range = [1, None] + page_range
        elif start == 2:
            page_range = [1] + page_range
        if end < paginator.num_pages:
            page_range = page_range + [None, paginator.num_pages]
        elif end == paginator.num_pages:
            page_range = page_range + [paginator.num_pages]

    context = {
        'tasks': tasks,
        'centres': centres,
        'centre_filter': centre_filter,
        'search_query': search_query,
        'items_per_page': items_per_page,
        'items_per_page_options': [10, 25, 50, 100, 500],
        'scope': scope,
        'page_range': page_range,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'overdue_tasks': overdue_tasks,
        'tasks_by_status': tasks_by_status,
        'tasks_by_activity': tasks_by_activity,
        'view_name': 'ppm_report',
    }
    return render(request, 'ppm/ppm_report.html', context)