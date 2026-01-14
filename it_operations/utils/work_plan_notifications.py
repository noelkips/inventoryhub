from datetime import date
from django.contrib.contenttypes.models import ContentType
from devices.models import Notification, CustomUser
from devices.utils import send_custom_email
from ..models import PublicHoliday

def get_kenyan_holidays(year=None):
    if not year:
        year = date.today().year
    return list(PublicHoliday.objects.filter(date__year=year).values_list('date', flat=True))

def notify_collaborator(task, new_collaborator):
    """
    Logic #4: Send Email & System Notification
    """
    # 1. System Notification
    Notification.objects.create(
        user=new_collaborator,
        message=f"You have been added as a collaborator to task: {task.task_name} on {task.date}",
        content_type=ContentType.objects.get_for_model(task),
        object_id=task.id
    )

    # 2. Email Notification
    subject = f"MOHI IT: New Collaboration Task - {task.date}"
    message = f"""
    Dear {new_collaborator.first_name},
    
    You have been added as a collaborator to the following task by {task.work_plan.user.get_full_name()}:
    
    Task: {task.task_name}
    Date: {task.date}
    Target: {task.target or 'N/A'}
    
    Please login to the dashboard to view details.
    """
    send_custom_email(subject, message, [new_collaborator.email])