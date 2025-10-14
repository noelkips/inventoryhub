from http.client import HTTPResponse
from venv import logger
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db import IntegrityError
from datetime import datetime
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

def is_superuser(user):
    return user.is_superuser

logger = logging.getLogger(__name__)



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


@login_required
def ppm_report(request):
    # Determine user permissions and base query
    if request.user.is_superuser:
        centres = Centre.objects.all()
        base_tasks_query = PPMTask.objects.select_related(
            'device', 'device__centre', 'device__department', 'period', 'created_by'
        ).prefetch_related('activities')
    elif request.user.centre:
        centres = Centre.objects.filter(id=request.user.centre.id)
        base_tasks_query = PPMTask.objects.filter(
            device__centre=request.user.centre
        ).select_related(
            'device', 'device__centre', 'device__department', 'period', 'created_by'
        ).prefetch_related('activities')
    else:
        centres = Centre.objects.none()
        base_tasks_query = PPMTask.objects.none()

    # Get filters
    centre_filter = request.GET.get('centre', '')
    search_query = request.GET.get('search', '').strip()
    items_per_page = request.GET.get('items_per_page', '10')
    page_number = request.GET.get('page', '1')
    export_type = request.GET.get('export', '')

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

    # Apply filters
    tasks_query = base_tasks_query.order_by('-created_at', 'id')

    # Centre filter
    if centre_filter:
        if request.user.is_superuser or str(request.user.centre.id) == centre_filter:
            tasks_query = tasks_query.filter(device__centre__id=centre_filter)

    # Search filter
    if search_query:
        query = (
            Q(device__serial_number__icontains=search_query) |
            Q(device__assignee_first_name__icontains=search_query) |
            Q(device__assignee_last_name__icontains=search_query) |
            Q(device__department__name__icontains=search_query) |
            Q(remarks__icontains=search_query) |
            Q(period__name__icontains=search_query) |
            Q(device__hardware__icontains=search_query)
        )
        tasks_query = tasks_query.filter(query)

    # Statistics
    total_tasks = tasks_query.count()
    completed_tasks = tasks_query.filter(completed_date__isnull=False).count()
    overdue_tasks = tasks_query.filter(
        period__end_date__lt=timezone.now().date(),
        completed_date__isnull=True
    ).count()
    tasks_by_status = {
        'Completed': completed_tasks,
        'Incomplete': total_tasks - completed_tasks
    }
    tasks_by_activity = tasks_query.values('activities__name').annotate(
        count=Count('id')
    ).order_by('-count')

    # Handle PDF Export - Export ALL filtered tasks
    if export_type == 'pdf':
        if not request.user.is_superuser and not centre_filter:
            messages.error(request, "Please select a centre to generate the report.")
            return redirect('ppm_report')
        
        # Get centre for report header
        centre = None
        if centre_filter:
            try:
                centre = Centre.objects.get(id=centre_filter)
                if not request.user.is_superuser and str(request.user.centre.id) != centre_filter:
                    messages.error(request, "You can only generate a report for your assigned centre.")
                    return redirect('ppm_report')
            except Centre.DoesNotExist:
                messages.error(request, "Invalid centre selected.")
                return redirect('ppm_report')
        elif request.user.centre:
            centre = request.user.centre

        # Get ALL filtered tasks for export (not just current page)
        export_tasks = list(tasks_query)
        
        if not export_tasks:
            messages.error(request, "No tasks available for the selected filters.")
            return redirect('ppm_report')

        try:
            response = HttpResponse(content_type='application/pdf')
            filename = f"PPM_Report_{centre.name if centre else 'All'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

            # Create PDF in landscape for better table layout
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
            
            # Custom styles
            styles.add(ParagraphStyle(
                name='ReportTitle',
                fontSize=18,
                leading=22,
                textColor=colors.HexColor('#143C50'),
                alignment=TA_CENTER,
                spaceAfter=6
            ))
            styles.add(ParagraphStyle(
                name='SubTitle',
                fontSize=12,
                leading=14,
                textColor=colors.HexColor('#143C50'),
                alignment=TA_CENTER,
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
                ['Total Tasks', str(total_tasks)],
                ['Completed Tasks', str(completed_tasks)],
                ['Incomplete Tasks', str(total_tasks - completed_tasks)],
                ['Overdue Tasks', str(overdue_tasks)],
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
                    'Done' if task.completed_date else 'Pending',
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

        except Exception as e:
            logger.error(f"PDF generation failed: {str(e)}")
            messages.error(request, f"Error generating PDF: {str(e)}")
            return redirect('ppm_report')

    # Handle Excel Export - Export ALL filtered tasks
    if export_type == 'excel':
        # Get ALL filtered tasks for export
        export_tasks = list(tasks_query)
        
        if not export_tasks:
            messages.error(request, "No tasks available for the selected filters.")
            return redirect('ppm_report')

        try:
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

            # Write headers
            headers = [
                'No.', 'Serial Number', 'Hardware', 'Centre', 'Department',
                'Assignee First Name', 'Assignee Last Name', 'Assignee Email',
                'Activities', 'Status', 'Completed Date', 'Remarks', 'Period',
                'Created By', 'Created At'
            ]
            
            for col, header in enumerate(headers):
                worksheet.write(0, col, header, header_format)

            # Write data
            for row, task in enumerate(export_tasks, 1):
                activities = ', '.join(task.activities.values_list('name', flat=True))
                
                worksheet.write(row, 0, row, cell_format)
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
            filename = f"PPM_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        except Exception as e:
            logger.error(f"Excel generation failed: {str(e)}")
            messages.error(request, f"Error generating Excel: {str(e)}")
            return redirect('ppm_report')

    # Pagination for display
    paginator = Paginator(tasks_query, items_per_page)
    try:
        tasks = paginator.page(page_number)
    except:
        tasks = paginator.page(1)

    context = {
        'tasks': tasks,
        'centres': centres,
        'centre_filter': centre_filter,
        'search_query': search_query,
        'items_per_page': items_per_page,
        'items_per_page_options': [10, 25, 50, 100, 500],
        'paginator': paginator,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'overdue_tasks': overdue_tasks,
        'tasks_by_status': tasks_by_status,
        'tasks_by_activity': tasks_by_activity,
        'view_name': 'ppm_report',
    }
    
    return render(request, 'ppm/ppm_report.html', context)