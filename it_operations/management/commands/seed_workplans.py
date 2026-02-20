from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from devices.models import Centre, Department
from it_operations.models import WorkPlan, WorkPlanTask, PublicHoliday

User = get_user_model()

class Command(BaseCommand):
    help = 'Creates 10 work plan tasks (5 per day) for John Mwangi on 19th and 20th February 2026'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING(
            'Creating 10 work plan tasks for John Mwangi (Mwangi@mohiafrica.org)...'
        ))

        # ---------------------------------------------------------
        # CONFIG
        # ---------------------------------------------------------
        task_dates = [date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19), date(2026, 2, 20)]  # 19th and 20th February 2026
        tasks_per_day = 1 # Total 10 tasks across the two days

        # ---------------------------------------------------------
        # TARGET USER
        # ---------------------------------------------------------
        try:
            john_mwangi = User.objects.get(email="samuel.kamande@mohiafrica.org")
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                "User Mwangi@mohiafrica.org not found."
            ))
            return

        centres = list(Centre.objects.all())
        departments = list(Department.objects.all())
        centre = centres[0] if centres else None
        department = departments[0] if departments else None

        # ---------------------------------------------------------
        # OPTIONAL: CLEAN EXISTING TASKS ON THESE DATES (UNCOMMENT IF NEEDED)
        # ---------------------------------------------------------
        # This will delete ALL existing tasks for this user on the specified dates.
        # Comment out if you want to preserve any existing tasks.
        # WorkPlanTask.objects.filter(
        #     work_plan__user=john_mwangi,
        #     date__in=task_dates
        # ).delete()

        # ---------------------------------------------------------
        # GENERATION
        # ---------------------------------------------------------
        task_index = 1

        with transaction.atomic():
            for task_date in task_dates:
                # Calculate Monday of the week containing this date
                monday = task_date - timedelta(days=task_date.weekday())

                # Get or create work plan for that week
                work_plan, _ = WorkPlan.objects.get_or_create(
                    user=john_mwangi,
                    week_start_date=monday,
                    defaults={
                        'week_end_date': monday + timedelta(days=5)
                    }
                )

                # Create 5 tasks for this date
                for _ in range(tasks_per_day):
                    task_name = f"Week 2 Task {task_index}"

                    WorkPlanTask.objects.create(
                        work_plan=work_plan,
                        date=task_date,
                        is_leave=False,
                        task_name=task_name,
                        centre=centre,
                        department=department,
                        other_parties=None,  # No collaborator specified; set a name/email if needed
                        resources_needed="As required",  # Customize if needed
                        target="Complete task",
                        comments=None,
                        status="Pending",
                        created_by=john_mwangi
                    )

                    task_index += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done! Created 10 tasks (5 on {task_dates[0]}, 5 on {task_dates[1]}) for John Mwangi."
        ))