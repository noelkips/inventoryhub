import io
import csv
import os
from datetime import datetime, date, timedelta
import calendar

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.conf import settings
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.contrib.auth import get_user_model

# ReportLab Imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# Internal Imports
from ..models import PublicHoliday, WorkPlan, WorkPlanTask
from devices.models import Centre, Department, CustomUser
from ..utils import get_kenyan_holidays, notify_collaborator

User = get_user_model()

# ============ PERMISSION HELPERS ============

def is_manager_of(user, target_user):
    """
    Determines if 'user' is a manager of 'target_user' based on hierarchy.
    """
    if user == target_user:
        return True
    # IT Manager manages IT Staff (non-trainers)
    if getattr(user, 'is_it_manager', False) and target_user.is_staff and not getattr(target_user, 'is_trainer', False):
        return True
    # Senior IT manages Trainers
    if getattr(user, 'is_senior_it_officer', False) and getattr(target_user, 'is_trainer', False):
        return True
    return False

def _get_next_working_day(from_date):
    """
    Returns the next working day (Mon-Sat), skipping Sundays and public holidays.
    """
    current = from_date + timedelta(days=1)
    while True:
        if current.weekday() == 6:  # Sunday
            current += timedelta(days=1)
            continue
        if PublicHoliday.objects.filter(date=current).exists():
            current += timedelta(days=1)
            continue
        return current


# ============ VIEWS ============

@login_required
def work_plan_list(request):
    user = request.user
    today = timezone.now().date()
    
    target_user = user 
    is_manager = getattr(user, 'is_it_manager', False)
    is_senior = getattr(user, 'is_senior_it_officer', False)
    users_to_filter = None

    if is_manager:
        users_to_filter = User.objects.filter(is_staff=True, is_active=True).exclude(is_trainer=True).order_by('first_name')
    elif is_senior:
        users_to_filter = User.objects.filter(is_trainer=True, is_active=True).order_by('first_name')

    filter_id = request.GET.get('user_filter')
    if filter_id and (is_manager or is_senior):
        try:
            target_user = User.objects.get(pk=filter_id)
        except User.DoesNotExist:
            pass
            
    current_week_start = today - timedelta(days=today.weekday())
    current_week_end = current_week_start + timedelta(days=6)
    
    current_tasks = WorkPlanTask.objects.filter(
        work_plan__user=target_user,
        date__range=[current_week_start, current_week_end]
    ).order_by('date')

    collab_tasks = WorkPlanTask.objects.filter(
        collaborators=target_user,
        date__gte=today
    ).order_by('date')

    plans = WorkPlan.objects.filter(user=target_user).order_by('-week_start_date')

    context = {
        'target_user': target_user,
        'users_to_filter': users_to_filter,
        'current_tasks': current_tasks,
        'collab_tasks': collab_tasks,
        'plans': plans,
        'is_viewing_others': user != target_user
    }
    return render(request, 'work_plan/workplan_list.html', context)

@login_required
def work_plan_detail(request, pk):
    """
    Detailed view of a specific Work Plan.
    Handles strict permission logic for Owner vs Manager vs Collaborator.
    """
    work_plan = get_object_or_404(WorkPlan, pk=pk)
    user = request.user
    today = timezone.now().date()
    
    # 1. Access Check
    is_owner = (user == work_plan.user)
    is_manager = is_manager_of(user, work_plan.user) and not is_owner
    is_collaborator_on_any = work_plan.tasks.filter(collaborators=user).exists()
    
    if not (is_owner or is_manager or is_collaborator_on_any):
        messages.error(request, "Access Denied.")
        return redirect('work_plan_list')

    # 2. Global "Can Add Task" Logic (Only Owner + before deadline)
    can_add_global = work_plan.can_add_tasks and is_owner
    
    # 3. Handle Add Task (POST)
    if request.method == 'POST' and 'add_task' in request.POST:
        if not can_add_global:
            messages.error(request, "Adding tasks is locked for this week.")
            return redirect('work_plan_detail', pk=pk)
        
        try:
            selected_date_str = request.POST.get('date')
            selected_date = date.fromisoformat(selected_date_str)
            is_leave = request.POST.get('is_leave') == 'on'
            
            # CASE: Adding "On Leave"
            if is_leave:
                # Get all tasks on this date
                all_tasks_on_date = WorkPlanTask.objects.filter(
                    work_plan=work_plan,
                    date=selected_date
                )
                
                # Move regular tasks
                regular_tasks = all_tasks_on_date.filter(is_leave=False)
                moved_count = 0
                
                if regular_tasks.exists():
                    next_day = _get_next_working_day(selected_date)
                    new_week_start = next_day - timedelta(days=next_day.weekday())
                    new_plan, _ = WorkPlan.objects.get_or_create(
                        user=work_plan.user,
                        week_start_date=new_week_start
                    )
                    
                    for old_task in regular_tasks:
                        new_task = WorkPlanTask.objects.create(
                            work_plan=new_plan,
                            date=next_day,
                            task_name=old_task.task_name,
                            centre=old_task.centre,
                            department=old_task.department,
                            resources_needed=old_task.resources_needed,
                            target=old_task.target,
                            other_parties=old_task.other_parties,
                            comments=f"Auto-rescheduled from {old_task.date} due to leave" +
                                     (f"\n{old_task.comments}" if old_task.comments else ""),
                            is_leave=False,
                            created_by=user,
                            status='Pending'
                        )
                        new_task.collaborators.set(old_task.collaborators.all())
                        moved_count += 1
                    
                    messages.info(request, f"{moved_count} task(s) successfully moved to {next_day}.")
                    # Delete original regular tasks
                    regular_tasks.delete()
                
                # Delete any existing leave task
                all_tasks_on_date.filter(is_leave=True).delete()
                
                # Create single "On Leave" placeholder
                WorkPlanTask.objects.create(
                    work_plan=work_plan,
                    date=selected_date,
                    task_name="On Leave",
                    is_leave=True,
                    created_by=user,
                    status='Pending',
                    resources_needed="N/A",
                    target="N/A"
                )
                messages.success(request, f"{selected_date} marked as On Leave.")
            
            # CASE: Adding normal task
            else:
                if WorkPlanTask.objects.filter(work_plan=work_plan, date=selected_date, is_leave=True).exists():
                    messages.error(request, f"Cannot add task on {selected_date}. This day is marked as 'On Leave'.")
                    return redirect('work_plan_detail', pk=pk)
                
                task = WorkPlanTask.objects.create(
                    work_plan=work_plan,
                    date=selected_date,
                    task_name=request.POST.get('task_name'),
                    centre_id=request.POST.get('centre') or None,
                    department_id=request.POST.get('department') or None,
                    resources_needed=request.POST.get('resources_needed'),
                    target=request.POST.get('target'),
                    other_parties=request.POST.get('other_parties'),
                    comments=request.POST.get('comments', ""),
                    is_leave=False,
                    created_by=user,
                    status='Pending'
                )
                
                collab_ids = request.POST.getlist('collaborators')
                if collab_ids:
                    task.collaborators.set(collab_ids)
                    for c_id in collab_ids:
                        try:
                            notify_collaborator(task, User.objects.get(pk=c_id))
                        except:
                            pass
                
                messages.success(request, "Task added successfully.")
        
        except Exception as e:
            messages.error(request, f"Error adding task: {str(e)}")
        
        return redirect('work_plan_detail', pk=pk)

    # 4. Process Tasks with Granular Permissions
    tasks = work_plan.tasks.all().select_related('centre', 'department').prefetch_related('collaborators')
    processed_tasks = []
    
    for t in tasks:
        is_task_collab = user in t.collaborators.all()
        
        if not (is_owner or is_manager or is_task_collab):
            continue 

        t.can_edit = is_owner or is_task_collab
        t.can_delete = is_owner or is_manager
        t.can_reschedule = is_owner or is_manager or is_task_collab
        t.can_change_status = (is_owner or is_manager or is_task_collab) and (t.date <= today)
        t.can_comment = True

        processed_tasks.append(t)

    # For dropdown blocking in template
    leave_dates = [
        task.date.strftime('%Y-%m-%d') 
        for task in work_plan.tasks.filter(is_leave=True)
    ]

    context = {
        'work_plan': work_plan,
        'tasks': processed_tasks,
        'can_add_tasks': can_add_global,
        'today_date': today,
        'centres': Centre.objects.all(),
        'departments': Department.objects.all(),
        'potential_collaborators': User.objects.filter(is_active=True).exclude(id=work_plan.user.id).order_by('first_name'),
        'week_days': [work_plan.week_start_date + timedelta(days=i) for i in range(6)],
        'all_users': User.objects.filter(is_active=True).order_by('first_name'),
        'leave_dates': leave_dates,
    }
    return render(request, 'work_plan/workplan_detail.html', context)

@login_required
def get_task_details_json(request, pk):
    """
    API endpoint for Edit Modal - returns task data in correct format.
    """
    task = get_object_or_404(WorkPlanTask, pk=pk)
    
    user = request.user
    is_owner = user == task.work_plan.user
    is_collab = user in task.collaborators.all()
    
    if not (is_owner or is_collab):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    data = {
        'id': task.id,
        'task_name': task.task_name,
        'date': task.date.strftime('%Y-%m-%d'),
        'centre': task.centre.id if task.centre else '',
        'department': task.department.id if task.department else '',
        'target': task.target or '',
        'resources_needed': task.resources_needed or '',
        'other_parties': task.other_parties or '',
        'is_leave': task.is_leave,
        'status': task.status,
        'collaborators': list(task.collaborators.values_list('id', flat=True)),
    }
    return JsonResponse(data)


@login_required
@require_POST
def work_plan_task_status_update(request, pk):
    task = get_object_or_404(WorkPlanTask, pk=pk)
    
    # 1. Date Security Check (Server-side enforcement)
    today = timezone.now().date()
    if task.date > today:
        messages.error(request, "Cannot mark future tasks as completed.")
        return redirect(request.META.get('HTTP_REFERER'))
        
    # 2. Permission Check
    user = request.user
    is_owner = (user == task.work_plan.user)
    is_manager = is_manager_of(user, task.work_plan.user)
    is_collab = user in task.collaborators.all()
    
    if is_owner or is_manager or is_collab:
        if task.status != 'Completed':
            task.status = 'Completed'
        else:
            task.status = 'Pending'
        task.save()
        messages.success(request, f"Task status updated.")
    else:
        messages.error(request, "Permission denied.")
        
    return redirect(request.META.get('HTTP_REFERER'))


@login_required
@require_POST
def work_plan_task_edit(request, pk):
    task = get_object_or_404(WorkPlanTask, pk=pk)
    user = request.user
    
    # Permission check
    is_owner = (user == task.work_plan.user)
    is_collab = user in task.collaborators.all()
    
    if not (is_owner or is_collab):
        messages.error(request, "Permission denied.")
        return redirect(request.META.get('HTTP_REFERER', 'work_plan_list'))

    try:
        new_is_leave = request.POST.get('is_leave') == 'on'
        current_is_leave = task.is_leave

        # CASE: Marking the day as "On Leave"
        if new_is_leave:
            # Get all tasks on this date
            all_tasks_on_date = WorkPlanTask.objects.filter(
                work_plan=task.work_plan,
                date=task.date
            )
            
            # Identify regular (non-leave) tasks to move
            regular_tasks = all_tasks_on_date.filter(is_leave=False)
            
            moved_count = 0
            if regular_tasks.exists():
                next_day = _get_next_working_day(task.date)
                new_week_start = next_day - timedelta(days=next_day.weekday())
                new_plan, _ = WorkPlan.objects.get_or_create(
                    user=task.work_plan.user,
                    week_start_date=new_week_start
                )
                
                # Copy each regular task to next working day
                for old_task in regular_tasks:
                    new_task = WorkPlanTask.objects.create(
                        work_plan=new_plan,
                        date=next_day,
                        task_name=old_task.task_name,
                        centre=old_task.centre,
                        department=old_task.department,
                        resources_needed=old_task.resources_needed,
                        target=old_task.target,
                        other_parties=old_task.other_parties,
                        comments=f"Auto-rescheduled from {old_task.date} due to leave" +
                                 (f"\n{old_task.comments}" if old_task.comments else ""),
                        is_leave=False,
                        created_by=user,
                        status='Pending'
                    )
                    new_task.collaborators.set(old_task.collaborators.all())
                    moved_count += 1
                
                messages.info(request, f"{moved_count} task(s) successfully moved to {next_day}.")
                
                # CRITICAL: DELETE the original regular tasks
                regular_tasks.delete()
            
            # Also delete any existing "On Leave" task to avoid duplicates
            all_tasks_on_date.filter(is_leave=True).delete()
            
            # Create single clean "On Leave" placeholder
            WorkPlanTask.objects.create(
                work_plan=task.work_plan,
                date=task.date,
                task_name="On Leave",
                is_leave=True,
                created_by=user,
                status='Pending',
                resources_needed="N/A",
                target="N/A"
            )
            
            messages.success(request, f"{task.date} is now marked as On Leave. All previous tasks have been moved.")
            return redirect(request.META.get('HTTP_REFERER', 'work_plan_list'))

        # CASE: Removing "On Leave" (converting back to normal task)
        elif current_is_leave and not new_is_leave:
            task.is_leave = False
            task.task_name = request.POST.get('task_name')
            task.target = request.POST.get('target')
            task.resources_needed = request.POST.get('resources_needed')
            task.other_parties = request.POST.get('other_parties')
            task.centre_id = request.POST.get('centre') or None
            task.department_id = request.POST.get('department') or None
            
            collab_ids = request.POST.getlist('collaborators')
            task.collaborators.set(collab_ids)
            
            task.save()
            messages.success(request, "Task updated — no longer on leave.")
            return redirect(request.META.get('HTTP_REFERER', 'work_plan_list'))

        # CASE: Normal edit (no change to leave status)
        else:
            task.task_name = request.POST.get('task_name')
            task.target = request.POST.get('target')
            task.resources_needed = request.POST.get('resources_needed')
            task.other_parties = request.POST.get('other_parties')
            task.centre_id = request.POST.get('centre') or None
            task.department_id = request.POST.get('department') or None
            
            collab_ids = request.POST.getlist('collaborators')
            task.collaborators.set(collab_ids)
            
            task.save()
            messages.success(request, "Task updated successfully.")
    
    except Exception as e:
        messages.error(request, f"Error updating task: {str(e)}")
    
    return redirect(request.META.get('HTTP_REFERER', 'work_plan_list'))

@login_required
@require_POST
def work_plan_task_reschedule(request, pk):
    task = get_object_or_404(WorkPlanTask, pk=pk)
    user = request.user
    
    # Permission: Owner OR Manager OR Collaborator
    is_owner = (user == task.work_plan.user)
    is_manager = is_manager_of(user, task.work_plan.user)
    is_collab = user in task.collaborators.all()
    
    if not (is_owner or is_manager or is_collab):
        messages.error(request, "Permission denied.")
        return redirect(request.META.get('HTTP_REFERER'))

    new_date_str = request.POST.get('reschedule_date')
    reason = request.POST.get('reschedule_reason', '').strip()
    
    if not reason:
        messages.error(request, "Reschedule reason is required.")
        return redirect(request.META.get('HTTP_REFERER'))
    
    try:
        new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        
        # 1. Find or Create Plan for the new week
        new_week_start = new_date - timedelta(days=new_date.weekday())
        new_plan, _ = WorkPlan.objects.get_or_create(user=task.work_plan.user, week_start_date=new_week_start)
        
        # 2. Create New Task with reason
        new_task = WorkPlanTask.objects.create(
            work_plan=new_plan,
            date=new_date,
            task_name=task.task_name,
            centre=task.centre,
            department=task.department,
            other_parties=task.other_parties,
            resources_needed=task.resources_needed,
            target=task.target,
            comments=f"Rescheduled from {task.date}: {reason}" + 
                     (f"\n{task.comments}" if task.comments else ""),
            reschedule_reason=reason,  # Save the reason
            created_by=user,
            status='Pending',
            is_leave=task.is_leave
        )
        new_task.collaborators.set(task.collaborators.all())
        
        # 3. Mark old task as Rescheduled
        task.status = 'Rescheduled'
        task.reschedule_reason = reason  # Also save on old task for audit
        task.save()
        
        messages.success(request, f"Task rescheduled to {new_date}. Reason: {reason}")
    except Exception as e:
        messages.error(request, f"Error: {e}")

    return redirect(request.META.get('HTTP_REFERER'))


@login_required
@require_POST
def work_plan_task_add_comment(request, pk):
    task = get_object_or_404(WorkPlanTask, pk=pk)
    # Anyone with visibility access (checked via detail view logic generally) can comment
    # For safety, basic check:
    if not (request.user == task.work_plan.user or is_manager_of(request.user, task.work_plan.user) or request.user in task.collaborators.all()):
         messages.error(request, "Permission denied.")
         return redirect('work_plan_list')

    new_comment = request.POST.get('new_comment')
    if new_comment:
        formatted = f"\n[{request.user.first_name}]: {new_comment}"
        task.comments = (task.comments or "") + formatted
        task.save()
        messages.success(request, "Comment added.")
    return redirect('work_plan_detail', pk=task.work_plan.pk)


@login_required
@require_POST
def work_plan_task_delete(request, pk):
    task = get_object_or_404(WorkPlanTask, pk=pk)
    user = request.user
    
    # Permission: Owner OR Manager only. Collaborators CANNOT delete.
    is_owner = (user == task.work_plan.user)
    is_manager = is_manager_of(user, task.work_plan.user)
    
    if is_owner or is_manager:
        task.delete()
        messages.success(request, "Task deleted.")
    else:
        messages.error(request, "Permission denied.")
    return redirect('work_plan_detail', pk=task.work_plan.pk)


@login_required
def work_plan_create(request):
    if request.method == 'POST':
        date_str = request.POST.get('week_start_date')
        week_start = datetime.strptime(date_str, '%Y-%m-%d').date()
        if week_start.weekday() != 0:
            messages.error(request, "Must start on Monday.")
            return redirect('work_plan_create')
            
        plan, created = WorkPlan.objects.get_or_create(user=request.user, week_start_date=week_start)
        return redirect('work_plan_detail', pk=plan.pk)
    return render(request, 'work_plan/workplan_create.html')

@login_required
def work_plan_calendar(request):
    today = timezone.now().date()
    now = timezone.now()
    
    # 1. Date Navigation
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except ValueError:
        year = today.year
        month = today.month
    
    # 2. Target User (Manager Logic)
    target_user = request.user
    filter_id = request.GET.get('user_filter')
    if filter_id and (getattr(request.user, 'is_it_manager', False) or 
                     getattr(request.user, 'is_senior_it_officer', False) or 
                     request.user.is_superuser):
        try:
            target_user = User.objects.get(pk=filter_id)
        except User.DoesNotExist:
            pass

    holidays = get_kenyan_holidays(year)
    
    # 3. Fetch Tasks for the Month
    tasks = WorkPlanTask.objects.filter(
        Q(work_plan__user=target_user) | Q(collaborators=target_user),
        date__year=year, 
        date__month=month
    ).distinct().select_related('work_plan')

    events = []
    for t in tasks:
        color_class = 'border-blue-500 bg-blue-100 text-blue-800'
        status_code = 'active'
        
        if t.is_leave: 
            color_class = 'border-yellow-500 bg-yellow-100 text-yellow-800'
            status_code = 'leave'
        elif t.status == 'Completed': 
            color_class = 'border-green-500 bg-green-100 text-green-800'
            status_code = 'completed'
        elif t.status == 'Not Done': 
            color_class = 'border-red-500 bg-red-100 text-red-800'
            status_code = 'not_done'
        elif target_user in t.collaborators.all(): 
            color_class = 'border-purple-500 bg-purple-100 text-purple-800'
            status_code = 'collab'
            
        events.append({
            'id': t.id, 
            'title': t.task_name, 
            'date': t.date, 
            'color': color_class,
            'status_code': status_code,
            'work_plan_id': t.work_plan.id
        })

    # 4. Build Calendar Grid
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdatescalendar(year, month)
    
    calendar_grid = []
    for week in month_days:
        week_data = []
        week_start = week[0]
        deadline_dt = datetime.combine(week_start, datetime.min.time()) + timedelta(hours=10)
        deadline = timezone.make_aware(deadline_dt)
        
        can_add_to_week = (now <= deadline) and (target_user == request.user)

        for day in week:
            day_events = [e for e in events if e['date'] == day]
            
            # Flags
            has_leave_task = any(e['status_code'] == 'leave' for e in day_events)
            all_pending = (len(day_events) > 0 and 
                          all(e['status_code'] == 'active' for e in day_events))  # 'active' = Pending
            
            week_data.append({
                'date': day, 
                'day_num': day.day, 
                'is_current_month': day.month == month,
                'is_today': day == today,
                'is_holiday': day in holidays, 
                'events': day_events,
                'can_add_task': can_add_to_week and (day >= today),
                'has_leave_task': has_leave_task,
                'all_pending': all_pending,
                'css_class': "bg-gray-50 text-gray-400" if (day.weekday() == 6 or day in holidays) else "bg-white"
            })
        calendar_grid.append(week_data)

    context = {
        'calendar_grid': calendar_grid,
        'month_name': calendar.month_name[month],
        'year': year, 'month': month,
        'prev_year': (date(year, month, 1) - timedelta(days=1)).year,
        'prev_month': (date(year, month, 1) - timedelta(days=1)).month,
        'next_year': (date(year, month, 28) + timedelta(days=10)).year,
        'next_month': (date(year, month, 28) + timedelta(days=10)).month,
        'target_user': target_user,
        'centres': Centre.objects.all(), 
        'departments': Department.objects.all(),
        'potential_collaborators': User.objects.filter(is_active=True).exclude(id=request.user.id).order_by('first_name'),
    }
    return render(request, 'work_plan/workplan_calendar.html', context)




@login_required
@require_POST
def work_plan_create_task_from_calendar(request):
    try:
        date_str = request.POST.get('date')
        task_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        week_start = task_date - timedelta(days=task_date.weekday())
        
        # Security: Check deadline
        deadline_dt = datetime.combine(week_start, datetime.min.time()) + timedelta(hours=10)
        if timezone.now() > timezone.make_aware(deadline_dt):
            messages.error(request, "Deadline passed for this week.")
            return redirect('work_plan_calendar')

        plan, _ = WorkPlan.objects.get_or_create(user=request.user, week_start_date=week_start)
        is_leave = request.POST.get('is_leave') == 'on'
        
        # CASE: Adding "On Leave"
        if is_leave:
            # Get all tasks on this date
            all_tasks_on_date = WorkPlanTask.objects.filter(
                work_plan=plan,
                date=task_date
            )
            
            regular_tasks = all_tasks_on_date.filter(is_leave=False)
            moved_count = 0
            
            if regular_tasks.exists():
                next_day = _get_next_working_day(task_date)
                new_week_start = next_day - timedelta(days=next_day.weekday())
                new_plan, _ = WorkPlan.objects.get_or_create(
                    user=request.user,
                    week_start_date=new_week_start
                )
                
                for old_task in regular_tasks:
                    new_task = WorkPlanTask.objects.create(
                        work_plan=new_plan,
                        date=next_day,
                        task_name=old_task.task_name,
                        centre=old_task.centre,
                        department=old_task.department,
                        resources_needed=old_task.resources_needed,
                        target=old_task.target,
                        other_parties=old_task.other_parties,
                        comments=f"Auto-rescheduled from {old_task.date} due to leave" +
                                 (f"\n{old_task.comments}" if old_task.comments else ""),
                        is_leave=False,
                        created_by=request.user,
                        status='Pending'
                    )
                    new_task.collaborators.set(old_task.collaborators.all())
                    moved_count += 1
                
                messages.info(request, f"{moved_count} task(s) moved to {next_day} due to leave.")
                regular_tasks.delete()
            
            # Remove old leave task
            all_tasks_on_date.filter(is_leave=True).delete()
            
            # Create new "On Leave"
            WorkPlanTask.objects.create(
                work_plan=plan,
                date=task_date,
                task_name="On Leave",
                is_leave=True,
                created_by=request.user,
                status='Pending',
                resources_needed="N/A",
                target="N/A"
            )
            messages.success(request, f"{task_date} marked as On Leave.")
        
        # CASE: Normal task
        else:
            if WorkPlanTask.objects.filter(work_plan=plan, date=task_date, is_leave=True).exists():
                messages.error(request, f"Cannot add task on {task_date}. This day is marked as 'On Leave'.")
                return redirect('work_plan_calendar')
            
            task = WorkPlanTask.objects.create(
                work_plan=plan,
                date=task_date,
                task_name=request.POST.get('task_name'),
                centre_id=request.POST.get('centre') or None,
                department_id=request.POST.get('department') or None,
                other_parties=request.POST.get('other_parties'),
                resources_needed=request.POST.get('resources_needed'),
                target=request.POST.get('target'),
                created_by=request.user,
                status='Pending'
            )
            
            collab_ids = request.POST.getlist('collaborators')
            if collab_ids:
                task.collaborators.set(collab_ids)
                for c_id in collab_ids:
                    try:
                        notify_collaborator(task, User.objects.get(pk=c_id))
                    except:
                        pass
            
            messages.success(request, "Task added successfully.")
    
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")

    return redirect('work_plan_calendar')


@login_required
def download_bulk_excel_report(request):
    filter_id = request.GET.get('user_filter')
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    report_type = request.GET.get('report_type', 'weekly')

    target_user = request.user
    if filter_id and (getattr(request.user, 'is_it_manager', False) or 
                     getattr(request.user, 'is_senior_it_officer', False) or 
                     request.user.is_superuser):
        try:
            target_user = User.objects.get(pk=filter_id)
        except:
            pass
         
    base_qs = WorkPlanTask.objects.filter(Q(work_plan__user=target_user) | Q(collaborators=target_user))

    if report_type == 'monthly': 
        tasks = base_qs.filter(date__year=year, date__month=month).order_by('date')
        filename = f"WorkPlan_{target_user.username}_{month}_{year}.csv"
    elif report_type == 'annual': 
        tasks = base_qs.filter(date__year=year).order_by('date')
        filename = f"WorkPlan_{target_user.username}_{year}_Annual.csv"
    else: 
        today = timezone.now().date()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        tasks = base_qs.filter(date__range=[start, end]).order_by('date')
        filename = f"WorkPlan_{target_user.username}_CurrentWeek.csv"

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    
    # Updated headers
    writer.writerow(['Date', 'Task', 'Centre', 'Dept', 'Collaborators', 'Other Parties', 'Status', 'Target', 'Resources', 'Comments (incl. Reschedule Reason)'])
    
    for t in tasks:
        collabs = ", ".join([u.first_name for u in t.collaborators.all()])
        
        # Combine comments + reschedule reason
        comments_parts = []
        if t.comments:
            comments_parts.append(t.comments.strip())
        if t.status == 'Rescheduled' and t.reschedule_reason:
            comments_parts.append(f"[Rescheduled Reason]: {t.reschedule_reason.strip()}")
        comments_display = " | ".join(comments_parts) if comments_parts else ""
        
        writer.writerow([
            t.date, 
            t.task_name, 
            t.centre.name if t.centre else '', 
            t.department.name if t.department else '',
            collabs,
            t.other_parties or '',
            t.status, 
            t.target or '',
            t.resources_needed or '',
            comments_display
        ])
    return response

@login_required
def download_workplan_pdf(request, pk):
    work_plan = get_object_or_404(WorkPlan, pk=pk)
    is_owner = (request.user == work_plan.user)
    is_manager = is_manager_of(request.user, work_plan.user)
    is_collab = work_plan.tasks.filter(collaborators=request.user).exists()
    
    if not (is_owner or is_manager or is_collab):
        messages.error(request, "Access denied.")
        return redirect('work_plan_list')

    period_str = f"{work_plan.week_start_date.strftime('%d %B %Y')} - {work_plan.week_end_date.strftime('%d %B %Y')}"

    pdf = _build_workplan_pdf(
        [work_plan],
        request.user,
        title=f"Work Plan: {work_plan.user.get_full_name()}",
        report_type="weekly",
        period_str=period_str
    )
    
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="WorkPlan_{work_plan.week_start_date}.pdf"'
    return response

def _build_workplan_pdf(work_plan_qs, user, title="Work Plan Report", report_type="weekly", period_str=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=1.2*inch,
        bottomMargin=0.8*inch,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch
    )
    
    DARK_BLUE = colors.HexColor('#143C50')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ReportTitle', fontSize=18, fontName='Helvetica-Bold', textColor=DARK_BLUE, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='SubHeader', fontSize=12, fontName='Helvetica', textColor=colors.grey, alignment=TA_CENTER, spaceAfter=20))
    styles.add(ParagraphStyle(name='CellText', fontSize=8, leading=10, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='CellHeader', fontSize=9, leading=11, fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_CENTER))

    story = []

    # Header Image (kept as requested)
    header_img_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'document_title_1.png')
    if os.path.exists(header_img_path):
        header_img = Image(header_img_path, width=19.5*cm, height=1.4*cm)
        header_img.hAlign = 'CENTER'
        story.append(header_img)
        story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("IT Department – Work Plan Report", styles['ReportTitle']))
    if period_str:
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(period_str, styles['SubHeader']))
    story.append(Spacer(1, 0.3*cm))

    # Table with adjusted column widths
    headers = ['Date', 'Task / Activity', 'Centre / Dept', 'Collaborators', 'Other Parties', 'Comments', 'Target', 'Status']
    header_row = [Paragraph(h, styles['CellHeader']) for h in headers]
    data = [header_row]

    tasks = WorkPlanTask.objects.filter(work_plan__in=work_plan_qs).order_by('date')

    for t in tasks:
        c_name = t.centre.name if t.centre else "N/A"
        d_name = t.department.name if t.department else "N/A"
        loc_str = f"<b>{c_name}</b><br/><i>{d_name}</i>"
        collabs = ", ".join([u.first_name for u in t.collaborators.all()]) if t.collaborators.exists() else "-"
        
        # Comments + Reschedule Reason
        comments_parts = []
        if t.comments:
            comments_parts.append(t.comments.strip())
        if t.status == 'Rescheduled' and t.reschedule_reason:
            comments_parts.append(f"[Rescheduled]: {t.reschedule_reason.strip()}")
        comments_display = "<br/>".join(comments_parts) if comments_parts else "-"

        status_color = "black"
        if t.status == 'Completed': status_color = "green"
        elif t.status == 'Not Done': status_color = "red"
        elif t.status == 'Rescheduled': status_color = "orange"
        status_str = f"<font color='{status_color}'>{t.status}</font>"

        task_name = f"<b>[ON LEAVE]</b> {t.task_name}" if t.is_leave else t.task_name

        row = [
            Paragraph(t.date.strftime('%d-%b'), styles['CellText']),
            Paragraph(task_name, styles['CellText']),
            Paragraph(loc_str, styles['CellText']),
            Paragraph(collabs, styles['CellText']),
            Paragraph(t.other_parties or '-', styles['CellText']),
            Paragraph(comments_display, styles['CellText']),
            Paragraph(t.target or '-', styles['CellText']),
            Paragraph(status_str, styles['CellText'])
        ]
        data.append(row)

    # Adjusted column widths: reduced Collaborators & Other Parties, increased Comments
    col_widths = [2*cm, 4.8*cm, 2.8*cm, 2.5*cm, 2.5*cm, 5*cm, 3*cm, 2*cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), DARK_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(table)


    def add_text_watermark(canvas_obj, doc):
        canvas_obj.saveState()
        canvas_obj.setFont('Helvetica', 28)
        canvas_obj.setFillColor(colors.HexColor('#143C50'))
        canvas_obj.setFillAlpha(0.05) 
        
        # Grid spacing configuration
        x_step = 3 * inch
        y_step = 1.5 * inch
        
        # Define the 'Body' boundary. 
        # On a landscape A4 (8.27 inches high), we stop drawing 
        # if the Y coordinate is above ~6.5 inches to clear the header.
        header_cutoff = 6.5 * inch

        for x in range(-2, 14, 4):  # Horizontal steps
            for y in range(-2, 10, 3): # Vertical steps
                
                # Check if the current grid point is below the header area
                current_y = y * inch
                if current_y < header_cutoff:
                    canvas_obj.saveState()
                    canvas_obj.translate(x * inch, current_y)
                    canvas_obj.rotate(45)
                    canvas_obj.drawCentredString(0, 0, "MOHI IT")
                    canvas_obj.restoreState()
                
        canvas_obj.restoreState()

    # Build the document
    doc.build(story, onFirstPage=add_text_watermark, onLaterPages=add_text_watermark)
    buffer.seek(0)
    return buffer.getvalue()

@login_required
def download_bulk_pdf_report(request):
    """
    Generates PDF reports (Weekly, Monthly, Annual) similar to Excel version
    """
    filter_id = request.GET.get('user_filter')
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    report_type = request.GET.get('report_type', 'weekly')

    target_user = request.user
    if filter_id and (getattr(request.user, 'is_it_manager', False) or 
                     getattr(request.user, 'is_senior_it_officer', False) or 
                     request.user.is_superuser):
        try:
            target_user = User.objects.get(pk=filter_id)
        except:
            pass

    base_qs = WorkPlan.objects.filter(user=target_user)

    if report_type == 'monthly':
        work_plans = base_qs.filter(week_start_date__year=year, week_start_date__month=month)
        period_str = f"{calendar.month_name[month]} {year}"
        filename = f"WorkPlan_{target_user.username}_{month}_{year}_Report.pdf"
    elif report_type == 'annual':
        work_plans = base_qs.filter(week_start_date__year=year)
        period_str = f"Annual Report {year}"
        filename = f"WorkPlan_{target_user.username}_{year}_Annual.pdf"
    else:  # weekly
        today = timezone.now().date()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        work_plans = base_qs.filter(week_start_date=start)
        period_str = f"Week {start.strftime('%d %b')} - {end.strftime('%d %b %Y')}"
        filename = f"WorkPlan_{target_user.username}_Week_{start.strftime('%Y%m%d')}.pdf"

    if not work_plans.exists():
        messages.error(request, "No data found for the selected period.")
        return redirect('work_plan_calendar')

    pdf = _build_workplan_pdf(
        list(work_plans),
        request.user,
        title=f"Work Plan Report - {target_user.get_full_name()}",
        report_type=report_type,
        period_str=period_str
    )

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
