from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction

from devices.models import Centre, Department
from it_operations.models import WorkPlan, WorkPlanTask, PublicHoliday

User = get_user_model()


class Command(BaseCommand):
    help = 'Creates a fixed work plan for Noel Langat (26–30 Jan 2026)'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING(
            'Creating FIXED work plan for Noel Langat (no collaborators)...'
        ))

        # ---------------------------------------------------------
        # CONFIG
        # ---------------------------------------------------------
        start_date = date(2026, 2, 9)  # Monday
        end_date = date(2026, 2, 13)    # Friday
        today = timezone.now().date()

        # ---------------------------------------------------------
        # TARGET USER
        # ---------------------------------------------------------
        try:
            user = User.objects.get(email="sylvia.wanjiru@mohiafrica.org")
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                "User noel.langat@mohiafrica.org not found."
            ))
            return

        centres = list(Centre.objects.all())
        departments = list(Department.objects.all())

        # ---------------------------------------------------------
        # CLEAN EXISTING TASKS (ONLY THIS USER + DATE RANGE)
        # ---------------------------------------------------------
        WorkPlanTask.objects.filter(
            work_plan__user=user,
            date__range=[start_date, end_date]
        ).delete()

        # ---------------------------------------------------------
        # TASK DEFINITIONS (2 PER DAY)
        # ---------------------------------------------------------
        daily_tasks = [
            "To be added",
        ]

        total_created = 0

        # ---------------------------------------------------------
        # GENERATION
        # ---------------------------------------------------------
        with transaction.atomic():
            current_date = start_date

            while current_date <= end_date:
                monday = current_date - timedelta(days=current_date.weekday())

                work_plan, _ = WorkPlan.objects.get_or_create(
                    user=user,
                    week_start_date=monday,
                    defaults={
                        'week_end_date': monday + timedelta(days=5)
                    }
                )

                for task_name in daily_tasks:
                    WorkPlanTask.objects.create(
                        work_plan=work_plan,
                        date=current_date,
                        is_leave=False,
                        task_name=task_name,
                        centre=centres[0] if centres else None,
                        department=departments[0] if departments else None,
                        other_parties=None,
                        resources_needed="Standard IT Toolkit",
                        target="Task completion",
                        comments=None,
                        status="Pending",
                        created_by=user
                    )
                    total_created += 1

                current_date += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(
            f"Done! Created {total_created} tasks for Noel "
            "(26–30 January 2026)."
        ))
