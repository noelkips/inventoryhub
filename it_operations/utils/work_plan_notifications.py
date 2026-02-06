from datetime import date
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from devices.models import Notification, CustomUser
from devices.utils import send_custom_email
from ..models import PublicHoliday

def get_kenyan_holidays(year=None):
    if not year:
        year = date.today().year
    return list(PublicHoliday.objects.filter(date__year=year).values_list('date', flat=True))


def notify_collaborator(task, new_collaborator):
    """
    UPDATED: Includes direct link to work plan
    """
    # 1. System Notification
    Notification.objects.create(
        user=new_collaborator,
        message=f"You have been added as a collaborator to task: {task.task_name} on {task.date}",
        content_type=ContentType.objects.get_for_model(task),
        object_id=task.id
    )

    # 2. Email Notification with LINK
    work_plan_url = f"{settings.SITE_URL}/work-plan/detail/{task.work_plan.id}/"
    
    subject = f"MOHI IT: New Collaboration Task - {task.date}"
    message = f"""
Dear {new_collaborator.first_name},

You have been added as a collaborator to the following task by {task.work_plan.user.get_full_name()}:

Task: {task.task_name}
Date: {task.date}
Centre: {task.centre.name if task.centre else 'N/A'}
Target: {task.target or 'N/A'}

Click here to view the full work plan and task details:
{work_plan_url}

Best regards,
MOHI IT Department
    """
    send_custom_email(subject, message, [new_collaborator.email])


def notify_comment_added(task, comment_text, added_by):
    """
    NEW FUNCTION: Notifies task owner and all collaborators when a comment is added
    """
    work_plan_url = f"{settings.SITE_URL}/work-plan/detail/{task.work_plan.id}/"
    
    # Collect all people to notify (owner + collaborators, excluding the person who added comment)
    recipients = []
    
    # Task owner
    if task.work_plan.user != added_by and task.work_plan.user.email:
        recipients.append(task.work_plan.user)
    
    # All collaborators (except the one who added comment)
    for collaborator in task.collaborators.all():
        if collaborator != added_by and collaborator.email:
            recipients.append(collaborator)
    
    # Remove duplicates
    recipients = list(set(recipients))
    
    if not recipients:
        return  # No one to notify
    
    # Create system notifications
    for user in recipients:
        Notification.objects.create(
            user=user,
            message=f"New comment on task '{task.task_name}' ({task.date}) by {added_by.get_full_name()}",
            content_type=ContentType.objects.get_for_model(task),
            object_id=task.id
        )
    
    # Send email to all recipients
    recipient_emails = [user.email for user in recipients]
    
    subject = f"MOHI IT: Comment Added to Task '{task.task_name}'"
    
    # Truncate comment if too long for email
    comment_preview = comment_text[:200] + "..." if len(comment_text) > 200 else comment_text
    
    message = f"""
Dear Team,

{added_by.get_full_name()} has added a comment to a task you're involved in:

Task: {task.task_name}
Date: {task.date}
Task Owner: {task.work_plan.user.get_full_name()}
Centre: {task.centre.name if task.centre else 'N/A'}
Status: {task.status}

Comment:
---
{comment_preview}
---

Click here to view the full task details and all comments:
{work_plan_url}

Best regards,
MOHI IT Department
    """
    
    send_custom_email(subject, message, recipient_emails)


def notify_task_status_changed(task, old_status, new_status, changed_by):
    """
    NEW FUNCTION: Notifies relevant parties when task status changes
    """
    work_plan_url = f"{settings.SITE_URL}/work-plan/detail/{task.work_plan.id}/"
    
    # Notify owner if someone else changed it
    recipients = []
    
    if task.work_plan.user != changed_by and task.work_plan.user.email:
        recipients.append(task.work_plan.user)
    
    # Notify collaborators
    for collaborator in task.collaborators.all():
        if collaborator != changed_by and collaborator.email:
            recipients.append(collaborator)
    
    recipients = list(set(recipients))
    
    if not recipients:
        return
    
    # System notifications
    for user in recipients:
        Notification.objects.create(
            user=user,
            message=f"Task '{task.task_name}' status changed from {old_status} to {new_status} by {changed_by.get_full_name()}",
            content_type=ContentType.objects.get_for_model(task),
            object_id=task.id
        )
    
    # Email
    recipient_emails = [user.email for user in recipients]
    
    subject = f"MOHI IT: Task Status Updated - {task.task_name}"
    message = f"""
Dear Team,

The status of a task you're involved in has been updated:

Task: {task.task_name}
Date: {task.date}
Previous Status: {old_status}
New Status: {new_status}
Updated By: {changed_by.get_full_name()}

Click here to view the task details:
{work_plan_url}

Best regards,
MOHI IT Department
    """
    
    send_custom_email(subject, message, recipient_emails)