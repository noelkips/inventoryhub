from django.core.management.base import BaseCommand
from it_operations.notifications import send_work_plan_deadline_notifications

class Command(BaseCommand):
    help = 'Send work plan deadline notifications to managers and senior officers'

    def handle(self, *args, **options):
        send_work_plan_deadline_notifications()
        self.stdout.write(self.style.SUCCESS('Work plan notifications sent successfully'))
