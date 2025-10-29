from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import datetime, timedelta, date
from django.db.models import Q, Count
from devices.models import Centre, Department
from .models import (MissionCriticalAsset, BackupRegistry, WorkPlan, WorkPlanTask, 
                     WorkPlanTaskComment, WorkPlanActivity, WorkPlanComment)
from django.contrib.auth import get_user_model
import calendar

User = get_user_model()

# ============ MISSION CRITICAL ASSETS VIEWS ============
@login_required
def mission_critical_list(request):
    """Display all mission critical assets"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to access Mission Critical Assets.")
        return redirect('dashboard')
    
    assets = MissionCriticalAsset.objects.all()
    
    category = request.GET.get('category')
    if category:
        assets = assets.filter(category=category)
    
    criticality = request.GET.get('criticality')
    if criticality:
        assets = assets.filter(criticality_level=criticality)
    
    search = request.GET.get('search')
    if search:
        assets = assets.filter(Q(name__icontains=search) | Q(notes__icontains=search))
    
    paginator = Paginator(assets, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'assets': page_obj.object_list,
        'categories': MissionCriticalAsset.CATEGORY_CHOICES,
        'criticality_levels': MissionCriticalAsset.CRITICALITY_LEVEL_CHOICES,
    }
    return render(request, 'it_operations/mission_critical/asset_list.html', context)


@login_required
def mission_critical_detail(request, pk):
    """Display asset details"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to access this.")
        return redirect('dashboard')
    
    asset = get_object_or_404(MissionCriticalAsset, pk=pk)
    context = {'asset': asset}
    return render(request, 'it_operations/mission_critical/asset_detail.html', context)


@login_required
def mission_critical_create(request):
    """Create a new mission critical asset"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to create assets.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        asset = MissionCriticalAsset(
            name=request.POST.get('name'),
            category=request.POST.get('category'),
            location_scope=request.POST.get('location_scope'),
            purpose_function=request.POST.get('purpose_function'),
            dependency_linked_system=request.POST.get('dependency_linked_system'),
            backup_recovery_method=request.POST.get('backup_recovery_method'),
            department_id=request.POST.get('department'),
            criticality_level=request.POST.get('criticality_level'),
            notes=request.POST.get('notes'),
            created_by=request.user
        )
        asset.save()
        messages.success(request, 'Mission Critical Asset created successfully!')
        return redirect('mission_critical_list')
    
    departments = Department.objects.all()
    context = {
        'action': 'Add',
        'departments': departments,
        'categories': MissionCriticalAsset.CATEGORY_CHOICES,
        'criticality_levels': MissionCriticalAsset.CRITICALITY_LEVEL_CHOICES,
    }
    return render(request, 'it_operations/mission_critical/asset_form.html', context)


@login_required
def mission_critical_update(request, pk):
    """Update a mission critical asset"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to update assets.")
        return redirect('dashboard')
    
    asset = get_object_or_404(MissionCriticalAsset, pk=pk)
    
    if request.method == 'POST':
        asset.name = request.POST.get('name')
        asset.category = request.POST.get('category')
        asset.location_scope = request.POST.get('location_scope')
        asset.purpose_function = request.POST.get('purpose_function')
        asset.dependency_linked_system = request.POST.get('dependency_linked_system')
        asset.backup_recovery_method = request.POST.get('backup_recovery_method')
        asset.department_id = request.POST.get('department')
        asset.criticality_level = request.POST.get('criticality_level')
        asset.notes = request.POST.get('notes')
        asset.save()
        messages.success(request, 'Mission Critical Asset updated successfully!')
        return redirect('mission_critical_detail', pk=asset.pk)
    
    departments = Department.objects.all()
    context = {
        'asset': asset,
        'action': 'Update',
        'departments': departments,
        'categories': MissionCriticalAsset.CATEGORY_CHOICES,
        'criticality_levels': MissionCriticalAsset.CRITICALITY_LEVEL_CHOICES,
    }
    return render(request, 'it_operations/mission_critical/asset_form.html', context)


@login_required
def mission_critical_delete(request, pk):
    """Delete confirmation for mission critical asset"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to delete assets.")
        return redirect('dashboard')
    
    asset = get_object_or_404(MissionCriticalAsset, pk=pk)
    
    if request.method == 'POST':
        asset.delete()
        messages.success(request, 'Mission Critical Asset deleted successfully!')
        return redirect('mission_critical_list')
    
    context = {'asset': asset}
    return render(request, 'it_operations/mission_critical/asset_confirm_delete.html', context)


# ============ BACKUP REGISTRY VIEWS ============
@login_required
def backup_registry_list(request):
    """Display all backup records with reports"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to access Backup Registry.")
        return redirect('dashboard')
    
    backups = BackupRegistry.objects.all()
    
    centre = request.GET.get('centre')
    if centre:
        backups = backups.filter(centre_id=centre)
    
    system = request.GET.get('system')
    if system:
        backups = backups.filter(system=system)
    
    # Get statistics
    total_backups = backups.count()
    backups_by_system = backups.values('system').annotate(count=Count('id')).order_by('-count')
    backups_by_centre = backups.values('centre__name').annotate(count=Count('id')).order_by('-count')
    
    paginator = Paginator(backups, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    centres = Centre.objects.all()
    context = {
        'page_obj': page_obj,
        'backups': page_obj.object_list,
        'centres': centres,
        'system_choices': BackupRegistry.SYSTEM_CHOICES,
        'total_backups': total_backups,
        'backups_by_system': backups_by_system,
        'backups_by_centre': backups_by_centre,
    }
    return render(request, 'it_operations/backup_registry/backup_list.html', context)


@login_required
def backup_registry_create(request):
    """Create a new backup record"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to create backup records.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        backup = BackupRegistry(
            system=request.POST.get('system'),
            centre_id=request.POST.get('centre'),
            done_by=request.user,
            comments=request.POST.get('comments')
        )
        backup.save()
        messages.success(request, 'Backup record created successfully!')
        return redirect('backup_registry_list')
    
    centres = Centre.objects.all()
    context = {
        'action': 'Add',
        'centres': centres,
        'system_choices': BackupRegistry.SYSTEM_CHOICES,
    }
    return render(request, 'it_operations/backup_registry/backup_form.html', context)


@login_required
def backup_registry_update(request, pk):
    """Update a backup record"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to update backup records.")
        return redirect('dashboard')
    
    backup = get_object_or_404(BackupRegistry, pk=pk)
    
    if request.method == 'POST':
        backup.system = request.POST.get('system')
        backup.centre_id = request.POST.get('centre')
        backup.comments = request.POST.get('comments')
        backup.save()
        messages.success(request, 'Backup record updated successfully!')
        return redirect('backup_registry_list')
    
    centres = Centre.objects.all()
    context = {
        'backup': backup,
        'action': 'Update',
        'centres': centres,
        'system_choices': BackupRegistry.SYSTEM_CHOICES,
    }
    return render(request, 'it_operations/backup_registry/backup_form.html', context)


@login_required
def backup_registry_delete(request, pk):
    """Delete confirmation for backup record"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to delete backup records.")
        return redirect('dashboard')
    
    backup = get_object_or_404(BackupRegistry, pk=pk)
    
    if request.method == 'POST':
        backup.delete()
        messages.success(request, 'Backup record deleted successfully!')
        return redirect('backup_registry_list')
    
    context = {'backup': backup}
    return render(request, 'it_operations/backup_registry/backup_confirm_delete.html', context)


# ============ WORK PLAN VIEWS ============
@login_required
def work_plan_list(request):
    """Display work plans - trainers see only their own, others see all"""
    if request.user.is_trainer:
        work_plans = WorkPlan.objects.filter(user=request.user)
    else:
        work_plans = WorkPlan.objects.all()
    
    if not request.user.is_trainer:
        user_id = request.GET.get('user')
        if user_id:
            work_plans = work_plans.filter(user_id=user_id)
    
    paginator = Paginator(work_plans, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    staff_users = User.objects.filter(is_staff=True, is_trainer=False)
    
    work_plans_data = []
    for plan in page_obj.object_list:
        work_plans_data.append({
            'id': plan.pk,
            'user_name': plan.user.get_full_name() or plan.user.username,
            'week_start': plan.week_start_date.strftime('%b %d'),
            'week_end': plan.week_end_date.strftime('%b %d, %Y'),
            'is_submitted': plan.tasks.exists(),
            'created_at': plan.created_at.strftime('%b %d, %Y'),
        })
    
    staff_users_data = []
    for user in staff_users:
        staff_users_data.append({
            'id': user.id,
            'name': user.get_full_name() or user.username,
        })
    
    context = {
        'page_obj': page_obj,
        'work_plans': work_plans_data,
        'staff_users': staff_users_data,
    }
    return render(request, 'it_operations/work_plan/workplan_list.html', context)


@login_required
def work_plan_detail(request, pk):
    """Display work plan details with day-based tasks"""
    work_plan = get_object_or_404(WorkPlan, pk=pk)
    
    if request.user.is_trainer and work_plan.user != request.user:
        messages.error(request, "You can only view your own work plan.")
        return redirect('work_plan_list')
    
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    tasks_by_day = {}
    
    for idx, day in enumerate(days_order):
        day_tasks = work_plan.tasks.filter(day=day).prefetch_related('comments')
        tasks_by_day[day] = {
            'tasks': list(day_tasks),
            'animation_delay': f'{idx * 0.1:.1f}s',
            'day_number': idx + 1,
        }
    
    user_full_name = work_plan.user.get_full_name() or work_plan.user.username
    
    context = {
        'work_plan': work_plan,
        'tasks_by_day': tasks_by_day,
        'days_order': days_order,
        'user_full_name': user_full_name,
        'can_edit': work_plan.is_editable() and work_plan.user == request.user,
        'week_start': work_plan.week_start_date.strftime('%b %d'),
        'week_end': work_plan.week_end_date.strftime('%b %d, %Y'),
    }
    return render(request, 'it_operations/work_plan/workplan_detail.html', context)


@login_required
def work_plan_create(request):
    """Create a new work plan for current week"""
    today = timezone.now().date()
    monday = today - timedelta(days=today.weekday())
    saturday = monday + timedelta(days=5)
    
    existing = WorkPlan.objects.filter(user=request.user, week_start_date=monday).first()
    if existing:
        return redirect('work_plan_detail', pk=existing.pk)
    
    if request.method == 'POST':
        work_plan = WorkPlan(
            user=request.user,
            week_start_date=monday,
            week_end_date=saturday
        )
        work_plan.save()
        
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        for day in days:
            task_text = request.POST.get(f'task_{day}')
            if task_text:
                WorkPlanTask.objects.create(
                    work_plan=work_plan,
                    day=day,
                    task_description=task_text
                )
        
        messages.success(request, 'Work plan created successfully!')
        return redirect('work_plan_detail', pk=work_plan.pk)
    
    days_data = []
    for idx, day in enumerate(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']):
        day_date = monday + timedelta(days=idx)
        days_data.append({
            'name': day,
            'number': idx + 1,
            'animation_delay': f'{idx * 0.1:.1f}s',
            'date': day_date.strftime('%a, %b %d'),
        })
    
    context = {
        'days': days_data,
        'week_start': monday.strftime('%A, %b %d'),
        'week_end': saturday.strftime('%A, %b %d, %Y'),
    }
    return render(request, 'it_operations/work_plan/workplan_form.html', context)


@login_required
def work_plan_update(request, pk):
    """Update a work plan"""
    work_plan = get_object_or_404(WorkPlan, pk=pk)
    
    if work_plan.user != request.user:
        messages.error(request, "You can only edit your own work plan.")
        return redirect('work_plan_list')
    
    if not work_plan.is_editable():
        messages.error(request, "This work plan can no longer be edited. You can only add comments.")
        return redirect('work_plan_detail', pk=work_plan.pk)
    
    if request.method == 'POST':
        work_plan.tasks.all().delete()
        
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        for day in days:
            task_text = request.POST.get(f'task_{day}')
            if task_text:
                WorkPlanTask.objects.create(
                    work_plan=work_plan,
                    day=day,
                    task_description=task_text
                )
        
        work_plan.save()
        messages.success(request, 'Work plan updated successfully!')
        return redirect('work_plan_detail', pk=work_plan.pk)
    
    days_data = []
    for idx, day in enumerate(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']):
        day_tasks = work_plan.tasks.filter(day=day)
        task_text = '\n'.join([t.task_description for t in day_tasks])
        days_data.append({
            'name': day,
            'number': idx + 1,
            'animation_delay': f'{idx * 0.1:.1f}s',
            'tasks': task_text,
        })
    
    context = {
        'work_plan': work_plan,
        'days': days_data,
        'week_start': work_plan.week_start_date.strftime('%A, %b %d'),
        'week_end': work_plan.week_end_date.strftime('%A, %b %d, %Y'),
    }
    return render(request, 'it_operations/work_plan/workplan_edit.html', context)


@login_required
def work_plan_add_task_comment(request, task_id):
    """Add a comment to a task"""
    task = get_object_or_404(WorkPlanTask, pk=task_id)
    
    if request.method == 'POST':
        comment_text = request.POST.get('comment')
        if comment_text:
            WorkPlanTaskComment.objects.create(
                task=task,
                user=request.user,
                comment=comment_text
            )
            messages.success(request, 'Comment added successfully!')
    
    return redirect('work_plan_detail', pk=task.work_plan.pk)


@login_required
def work_plan_calendar(request, user_id=None):
    """Display work plan calendar for a user with monthly view"""
    if user_id:
        user = get_object_or_404(User, pk=user_id)
        if request.user.is_trainer and user != request.user:
            messages.error(request, "You can only view your own calendar.")
            return redirect('work_plan_list')
    else:
        user = request.user
    
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
    work_plans = WorkPlan.objects.filter(
        user=user,
        week_start_date__year=year,
        week_start_date__month__lte=month,
        week_end_date__month__gte=month
    )
    
    # Build calendar with work plan status
    cal = calendar.monthcalendar(year, month)
    
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    
    # Mark days with work plans
    work_plan_dates = {}
    for wp in work_plans:
        for day in range((wp.week_end_date - wp.week_start_date).days + 1):
            current_date = wp.week_start_date + timedelta(days=day)
            if current_date.month == month:
                has_tasks = wp.tasks.filter(day=calendar.day_name[current_date.weekday()]).exists()
                work_plan_dates[current_date.day] = {
                    'has_tasks': has_tasks,
                    'work_plan': wp,
                    'is_past_deadline': not wp.is_editable(),
                    'status': 'Submitted' if has_tasks else ('Overdue' if not wp.is_editable() else 'Pending'),
                    'status_color': 'green' if has_tasks else ('red' if not wp.is_editable() else 'yellow'),
                }
    
    work_plans_data = []
    for wp in work_plans:
        task_count = wp.tasks.count()
        work_plans_data.append({
            'id': wp.pk,
            'week_start': wp.week_start_date.strftime('%b %d'),
            'week_end': wp.week_end_date.strftime('%b %d, %Y'),
            'task_count': task_count,
            'is_submitted': task_count > 0,
        })
    
    context = {
        'user': user,
        'user_name': user.get_full_name() or user.username,
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'calendar': cal,
        'work_plan_dates': work_plan_dates,
        'today': today,
        'day_names': day_names,
        'work_plans': work_plans_data,
    }
    return render(request, 'it_operations/work_plan/workplan_calendar.html', context)


@login_required
def work_plan_reports(request):
    """Display work plan reports"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to view reports.")
        return redirect('dashboard')
    
    # Get filter parameters
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    user_id = request.GET.get('user')
    
    # Base queryset
    work_plans = WorkPlan.objects.filter(
        week_start_date__year=year,
        week_start_date__month__lte=month,
        week_end_date__month__gte=month
    )
    
    if user_id:
        work_plans = work_plans.filter(user_id=user_id)
    
    # Calculate statistics
    total_users = work_plans.values('user').distinct().count()
    submitted_plans = work_plans.filter(tasks__isnull=False).distinct().count()
    pending_plans = work_plans.filter(tasks__isnull=True).distinct().count()
    
    # Get users without work plans
    all_staff = User.objects.filter(is_staff=True, is_trainer=False)
    users_with_plans = work_plans.values_list('user_id', flat=True).distinct()
    users_without_plans = all_staff.exclude(id__in=users_with_plans)
    
    # Get work plans by user
    plans_by_user = work_plans.values('user__first_name', 'user__last_name', 'user__id').annotate(
        count=Count('id'),
        submitted=Count('tasks', distinct=True)
    ).order_by('-count')
    
    staff_users = all_staff
    
    context = {
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'total_users': total_users,
        'submitted_plans': submitted_plans,
        'pending_plans': pending_plans,
        'users_without_plans': users_without_plans,
        'plans_by_user': plans_by_user,
        'staff_users': staff_users,
    }
    return render(request, 'it_operations/work_plan/workplan_reports.html', context)
