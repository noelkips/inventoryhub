from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from devices.models import Centre, Department
from it_operations.models import WorkPlan, WorkPlanTask, PublicHoliday

User = get_user_model()

class Command(BaseCommand):
    help = 'Creates a work plan task for Santana Macharia on Monday 9th Feb 2026'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING(
            'Creating work plan task for Santana Macharia with Noel as collaborator...'
        ))

        # ---------------------------------------------------------
        # CONFIG
        # ---------------------------------------------------------
        task_date = date(2026, 2, 9)  # Monday 9th Feb
        today = timezone.now().date()

        # ---------------------------------------------------------
        # TARGET USER AND COLLABORATOR
        # ---------------------------------------------------------
        try:
            santana = User.objects.get(email="santana.macharia@mohiafrica.org")
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                "User santana.macharia@mohiafrica.org not found."
            ))
            return

        try:
            noel = User.objects.get(email="noel.langat@mohiafrica.org")
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                "User noel.langat@mohiafrica.org not found."
            ))
            return

        centres = list(Centre.objects.all())
        departments = list(Department.objects.all())

        # ---------------------------------------------------------
        # CLEAN EXISTING TASK (IF ANY)
        # ---------------------------------------------------------
        WorkPlanTask.objects.filter(
            work_plan__user=santana,
            date=task_date,
            task_name="Prepare user training document for library system"
        ).delete()

        # ---------------------------------------------------------
        # GENERATION
        # ---------------------------------------------------------
        with transaction.atomic():
            # Calculate Monday of the week
            monday = task_date - timedelta(days=task_date.weekday())
            
            # Get or create work plan for that week
            work_plan, _ = WorkPlan.objects.get_or_create(
                user=santana,
                week_start_date=monday,
                defaults={
                    'week_end_date': monday + timedelta(days=5)
                }
            )

            # Create the task
            task = WorkPlanTask.objects.create(
                work_plan=work_plan,
                date=task_date,
                is_leave=False,
                task_name="Prepare user training document for library system",
                centre=centres[0] if centres else None,
                department=departments[0] if departments else None,
                other_parties=noel.get_full_name() or noel.email,  # Noel as collaborator
                resources_needed="LMS",
                target="Complete task",
                comments=None,
                status="Pending",
                created_by=santana
            )

        self.stdout.write(self.style.SUCCESS(
            f"Done! Created task for Santana Macharia on {task_date} with Noel as collaborator."
        ))