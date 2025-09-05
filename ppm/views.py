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
    except ValueError:
        items_per_page = 10

    active_period = PPMPeriod.objects.filter(is_active=True).first()
    if not active_period:
        devices = Import.objects.none()
        messages.warning(request, "No active PPM period. Please create and activate a period.")
    else:
        devices = Import.objects.all(is_disposed=False, is_approved=True)
        if search_query:
            devices = devices.filter(
                Q(serial_number__icontains=search_query) |
                Q(assignee_first_name__icontains=search_query) |
                Q(assignee_last_name__icontains=search_query) |
                Q(department__icontains=search_query)
            )
        if centre_filter and centre_filter != '':
            devices = devices.filter(centre_id=centre_filter)

        # Check for existing PPM tasks in the active period
        for device in devices:
            device.has_ppm_task = PPMTask.objects.filter(device=device, period=active_period).exists()

    paginator = Paginator(devices, items_per_page)
    page_number = request.GET.get('page')
    devices = paginator.get_page(page_number)

    activities = active_period.activities.all() if active_period else []

    report_data = {
        'search_query': search_query,
        'centre_filter': centre_filter,
        'items_per_page': items_per_page,
        'total_records': devices.paginator.count,
    }

    context = {
        'devices': devices,
        'report_data': report_data,
        'centres': centres,
        'activities': activities,
        'active_period': active_period,
        'items_per_page_options': [5, 10, 20, 50],
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
        active_period = PPMPeriod.objects.filter(is_active=True).first()
        if not active_period:
            return JsonResponse({'error': 'No active PPM period.'}, status=400)
        task = get_object_or_404(PPMTask, device_id=device_id, period=active_period)
        data = {
            'activities': list(task.activities.values_list('id', flat=True)),
            'completed_date': task.completed_date.strftime('%Y-%m-%d') if task.completed_date else '',
            'remarks': task.remarks or '',
        }
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
        for field in ['device__serial_number', 'device__assignee_first_name', 'device__assignee_last_name', 'device__department']:
            query |= Q(**{f'{field}__icontains': search_query}) & ~Q(**{f'{field}__isnull': True}) & ~Q(**{f'{field}': ''})
        tasks = tasks.filter(query)
    if centre_filter:
        tasks = tasks.filter(device__centre__id=centre_filter)

    # Pagination
    items_per_page = request.GET.get('items_per_page', '10')
    try:
        items_per_page = int(items_per_page)
        if items_per_page not in [10, 25, 50, 100, 500]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    paginator = Paginator(tasks, items_per_page)
    page_number = request.GET.get('page', 1)
    try:
        page_number = int(page_number)
    except ValueError:
        page_number = 1
    try:
        tasks_on_page = paginator.page(page_number)
    except:
        tasks_on_page = paginator.page(1)

    centres = Centre.objects.all() if request.user.is_superuser else Centre.objects.filter(id=request.user.centre.id) if request.user.centre else Centre.objects.none()
    items_per_page_options = [10, 25, 50, 100, 500]
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
        'items_per_page_options': items_per_page_options,
        'report_data': report_data,
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