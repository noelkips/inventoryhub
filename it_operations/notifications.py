from django.utils import timezone
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from centre.models import Notification
from .models import WorkPlan

User = get_user_model()

def send_work_plan_deadline_notifications():
    """
    Send notifications to users who haven't submitted their work plan by Monday 10 AM.
    Managers get notified about staff, Senior IT Officers get notified about trainers.
    """
    now = timezone.now()
    
    # Get current week's Monday
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    
    # Check if it's past Monday 10 AM
    monday_10am = timezone.make_aware(datetime.combine(monday, datetime.min.time()).replace(hour=10))
    
    if now > monday_10am:
        # Get all staff users (not trainers)
        staff_users = User.objects.filter(is_staff=True, is_trainer=False)
        
        # Get all trainers
        trainers = User.objects.filter(is_trainer=True)
        
        # Check staff users who haven't submitted
        for staff_user in staff_users:
            work_plan = WorkPlan.objects.filter(user=staff_user, week_start_date=monday).first()
            
            if not work_plan or not work_plan.is_submitted():
                # Notify IT Managers
                managers = User.objects.filter(is_it_manager=True)
                for manager in managers:
                    message = f"{staff_user.get_full_name() or staff_user.username} has not submitted their work plan for the week of {monday.strftime('%B %d, %Y')}."
                    
                    # Check if notification already exists
                    existing = Notification.objects.filter(
                        user=manager,
                        message=message,
                        created_at__date=now.date()
                    ).exists()
                    
                    if not existing:
                        Notification.objects.create(
                            user=manager,
                            message=message
                        )
        
        # Check trainers who haven't submitted
        for trainer in trainers:
            work_plan = WorkPlan.objects.filter(user=trainer, week_start_date=monday).first()
            
            if not work_plan or not work_plan.is_submitted():
                # Notify Senior IT Officers
                senior_officers = User.objects.filter(is_senior_it_officer=True)
                for officer in senior_officers:
                    message = f"Trainer {trainer.get_full_name() or trainer.username} has not submitted their work plan for the week of {monday.strftime('%B %d, %Y')}."
                    
                    # Check if notification already exists
                    existing = Notification.objects.filter(
                        user=officer,
                        message=message,
                        created_at__date=now.date()
                    ).exists()
                    
                    if not existing:
                        Notification.objects.create(
                            user=officer,
                            message=message
                        )
