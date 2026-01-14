from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
# Import your existing notification function
from it_operations.notifications import send_work_plan_deadline_notifications
# Import models for the new logic
from devices.models import CustomUser, Notification 

class Command(BaseCommand):
    help = 'Sends work plan deadline notifications and Friday reminders'

    def handle(self, *args, **options):
        today = timezone.now()
        
        # 1. Run existing Manager/Senior Officer Notifications
        self.stdout.write("Sending Manager/Senior Officer notifications...")
        try:
            send_work_plan_deadline_notifications()
            self.stdout.write(self.style.SUCCESS(' - Manager notifications sent.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f' - Error sending manager notifications: {str(e)}'))

        # 2. New Logic: Friday Reminder for Staff (Logic #4)
        # Checks if today is Friday (Weekday 4)
        if today.weekday() == 4:
            self.stdout.write("Sending Friday Reminders to Staff...")
            
            # Target: Active Staff and Trainers
            users = CustomUser.objects.filter(is_active=True).filter(
                Q(is_staff=True) | Q(is_trainer=True)
            )
            
            count = 0
            for user in users:
                # Avoid duplicates if run multiple times
                recent_notif = Notification.objects.filter(
                    user=user,
                    message__startswith="Reminder: Please update your tasks",
                    created_at__date=today.date()
                ).exists()
                
                if not recent_notif:
                    Notification.objects.create(
                        user=user,
                        message="Reminder: Please update your tasks for this week and submit your plan for next week before Monday 10 AM."
                    )
                    count += 1
            
            self.stdout.write(self.style.SUCCESS(f' - Sent {count} Friday reminders.'))
        else:
            self.stdout.write("Not Friday; skipping staff reminders.")