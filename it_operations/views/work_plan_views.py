from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Q
from datetime import datetime, timedelta
from ..models import WorkPlan, WorkPlanTask, User
from devices.models import Centre, Department
import json

def get_available_humans(user):
    """Filter human resources based on user role"""
    if user.is_trainer:
        # Trainers see IT Senior and IT Manager
        return User.objects.filter(
            Q(is_senior_it_officer=True) | Q(is_it_manager=True)
        )
    elif hasattr(user, 'is_it_staff') and user.is_it_staff:
        # IT Staff see all IT personnel (IT Senior, Manager, and Staff)
        return User.objects.filter(
            Q(is_senior_it_officer=True) | Q(is_it_manager=True) | Q(is_staff=True)
        )
    else:
        return User.objects.none()


def can_add_for_week(user, week_start_date):
    """Check if user can add tasks for a specific week"""
    now = timezone.now()
    
    # Can always add for future weeks
    if week_start_date > now.date():
        return True, "You can add tasks for future weeks"
    
    # For current week, check Monday 10 AM deadline
    next_monday = week_start_date + timedelta(days=7)
    deadline = timezone.make_aware(
        datetime.combine(next_monday, datetime.min.time()).replace(hour=10)
    )
    
    if now < deadline:
        return True, "Work plan is still editable"
    
    return False, "Deadline passed (Monday 10 AM)"


@login_required
def work_plan_calendar(request, year=None, month=None):
    """Display calendar view of work plans"""
    if year is None or month is None:
        today = timezone.now().date()
        year, month = today.year, today.month
    
    # Get all work plans for the user
    work_plans = WorkPlan.objects.filter(user=request.user)
    
    context = {
        'work_plans': work_plans,
        'year': year,
        'month': month,
    }
    return render(request, 'it_operations/work_plan/workplan_calendar.html', context)


@login_required
def work_plan_detail(request, pk):
    """Display detailed view of a work plan with all tasks"""
    work_plan = get_object_or_404(WorkPlan, pk=pk, user=request.user)
    
    # Group tasks by day
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    tasks_by_day = {}
    
    for day in days:
        day_date = work_plan.week_start_date + timedelta(days=days.index(day))
        tasks_by_day[day] = {
            'date': day_date,
            'tasks': work_plan.tasks.filter(day=day).order_by('created_at'),
            'day_num': days.index(day)
        }
    
    # Determine if work plan is editable
    is_editable = work_plan.is_editable()
    can_add, message = can_add_for_week(request.user, work_plan.week_start_date)
    
    context = {
        'work_plan': work_plan,
        'tasks_by_day': tasks_by_day,
        'is_editable': is_editable and can_add,
        'available_humans': get_available_humans(request.user),
        'available_centres': Centre.objects.all(),
        'available_departments': Department.objects.all(),
    }
    return render(request, 'it_operations/work_plan/workplan_detail.html', context)


@login_required
@require_http_methods(["POST"])
def add_task(request, pk):
    """AJAX endpoint to add a new task to work plan"""
    work_plan = get_object_or_404(WorkPlan, pk=pk, user=request.user)
    
    # Check deadline
    can_add, message = can_add_for_week(request.user, work_plan.week_start_date)
    if not can_add:
        return JsonResponse({'success': False, 'error': message}, status=403)
    
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        if not data.get('task_name') or not data.get('day'):
            return JsonResponse({'success': False, 'error': 'Task name and day are required'}, status=400)
        
        # Create task
        task = WorkPlanTask.objects.create(
            work_plan=work_plan,
            day=data['day'],
            task_name=data['task_name'],
            centre_id=data.get('centre') or None,
            department_id=data.get('department') or None,
            items_needed=data.get('items_needed', ''),
            comments=data.get('comments', ''),
            target=data.get('target', ''),
            status='Not Done',
            created_by=request.user,
        )
        
        # Add human resources
        if data.get('human_resources'):
            human_ids = data['human_resources']
            if isinstance(human_ids, str):
                human_ids = [int(x) for x in human_ids.split(',') if x.strip()]
            task.human_resources.set(human_ids)
        
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'message': 'Task added successfully'
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def update_task_status(request, pk):
    """AJAX endpoint to update task status"""
    task = get_object_or_404(WorkPlanTask, pk=pk)
    
    # Check permissions
    work_plan = task.work_plan
    if work_plan.user != request.user and not request.user.is_it_manager:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    # Check if user can edit this task
    if not request.user.is_it_manager:
        week_status = work_plan.get_current_week_status()
        if week_status != 'current':
            return JsonResponse({'success': False, 'error': 'Cannot edit tasks outside current week'}, status=403)
    
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        
        if new_status not in dict(WorkPlanTask.STATUS_CHOICES):
            return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
        
        task.status = new_status
        task.status_updated_by = request.user
        task.save()
        
        return JsonResponse({
            'success': True,
            'status': task.status,
            'color_class': task.get_status_color()
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["DELETE"])
def delete_task(request, pk):
    """AJAX endpoint to delete a task"""
    task = get_object_or_404(WorkPlanTask, pk=pk)
    
    # Check permissions
    work_plan = task.work_plan
    if work_plan.user != request.user and not request.user.is_it_manager:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    # Check deadline
    can_add, message = can_add_for_week(request.user, work_plan.week_start_date)
    if not can_add and work_plan.user == request.user:
        return JsonResponse({'success': False, 'error': message}, status=403)
    
    try:
        task_id = task.id
        task.delete()
        return JsonResponse({'success': True, 'task_id': task_id})
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

# it_operations/views/work_plan_views.py

def work_plan_list(request):
    work_plans = WorkPlan.objects.prefetch_related('tasks').all()

    # Add counts to each work plan
    for wp in work_plans:
        wp.completed_count = wp.tasks.filter(status='Completed').count()
        wp.not_completed_count = wp.tasks.filter(status='Not Completed').count()
        wp.not_done_count = wp.tasks.filter(status='Not Done').count()

    return render(request, 'it_operations/work_plan/workplan_list.html', {
        'work_plans': work_plans
    })