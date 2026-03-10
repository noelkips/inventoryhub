
""""
# Daily overdue reminders (every day at 7 AM) + Monday missing-tasks reminder (only on Mondays at 7 AM)
0 7 * * * cd /home/ufdxwals/inventoryhub && /home/ufdxwals/virtualenv/inventoryhub/3.10/bin/python -X utf8 manage.py send_workplan_reminders >> /home/ufdxwals/inventoryhub/logs/reminders.log 2>&1

"""


import calendar
from collections import defaultdict
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from django.db.models import Q
from it_operations.models import WorkPlan, WorkPlanTask  # Correct import
from devices.models import CustomUser
from devices.utils.emails import send_custom_email  # Central email utility


class Command(BaseCommand):
    help = (
        'Sends reminders:\n'
        '- Daily: For pending tasks overdue by 7+ days (to owner + collaborators) - SKIPS leave days\n'
        '- Monday 7 AM: For users missing tasks in the current week (Monday-Friday) - leave days are considered covered'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Log actions without sending emails')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = timezone.now().date()
        current_day = today.weekday()  # 0=Monday, 6=Sunday

        if settings.DEBUG:
            base_url = 'http://localhost:8000'  # Use localhost for development
        else:
            if settings.DATABASES.get('default') and settings.DATABASES.get('default', {}).get('NAME') == 'ufdxwals_it_test_db':
                base_url = 'https://test.mohiit.org'
            else:
                base_url = 'https://mohiit.org'  # Default fallback URL

        sent_count = 0

        # ============ 1. Overdue Pending Tasks Reminder (runs daily) ============
        overdue_date = today - timedelta(days=7)
        overdue_tasks = WorkPlanTask.objects.filter(
            status='Pending',
            date__lte=overdue_date,
            is_leave=False  # Explicitly skip leave tasks
        ).select_related('work_plan__user').prefetch_related('collaborators')

        if overdue_tasks.exists():
            self.stdout.write(f"Found {overdue_tasks.count()} overdue pending (non-leave) tasks.")

            recipient_to_tasks = defaultdict(list)  # email -> list[(task, link)]
            for task in overdue_tasks:
                involved_emails = set()

                owner = task.work_plan.user
                if owner and owner.email:
                    involved_emails.add(owner.email)

                for collab in task.collaborators.all():
                    if collab.email:
                        involved_emails.add(collab.email)

                if not involved_emails:
                    continue

                task_link = f"{base_url}{reverse('work_plan_detail', kwargs={'pk': task.work_plan.pk})}#task-{task.pk}"
                for email in involved_emails:
                    recipient_to_tasks[email].append((task, task_link))

            if recipient_to_tasks:
                self.stdout.write(f"Preparing combined overdue reminders for {len(recipient_to_tasks)} recipient(s).")

            for email, items in recipient_to_tasks.items():
                items.sort(key=lambda x: (x[0].date or date.max, x[0].pk))

                task_lines = []
                for idx, (task, task_link) in enumerate(items, start=1):
                    centre_name = task.centre.name if task.centre else 'N/A'
                    dept_name = task.department.name if task.department else 'N/A'
                    due_str = task.date.strftime('%d %b %Y') if task.date else 'N/A'
                    week_str = f"{task.work_plan.week_start_date.strftime('%d %b %Y')} - {task.work_plan.week_end_date.strftime('%d %b %Y')}"
                    task_lines.append(
                        f"{idx}. {task.task_name} | Due: {due_str} | Week: {week_str} | Centre: {centre_name} | Dept: {dept_name}\n"
                        f"   Link: {task_link}"
                    )

                message = f"""
Dear Team Member,

REMINDER: Overdue Pending Tasks (7+ days past due date)

You have {len(items)} overdue pending task(s). Please update the status or take action on each item below:

{chr(10).join(task_lines)}

Work Plan list: {base_url}{reverse('work_plan_list')}

Thank you.

IT Operations System
                """.strip()

                subject = f"[OVERDUE REMINDER] {len(items)} Pending Task(s) Overdue"

                if not dry_run:
                    success = send_custom_email(
                        subject=subject,
                        message=message,
                        recipient_list=[email]
                    )
                    if success:
                        sent_count += 1
                else:
                    self.stdout.write(
                        self.style.NOTICE(
                            f"[DRY-RUN] Would send 1 combined overdue reminder to {email} ({len(items)} task(s))"
                        )
                    )

        # ============ 2. Monday Reminder for Missing Weekly Tasks ============
        if current_day == 0:  # Monday
            self.stdout.write("Today is Monday - checking for missing weekly tasks.")

            week_start = today  # Current Monday
            week_end = week_start + timedelta(days=4)  # Friday

            work_days = []
            current = week_start
            while current <= week_end:
                work_days.append(current)
                current += timedelta(days=1)

            users = CustomUser.objects.filter(is_active=True).filter(
                Q(is_staff=True) | Q(is_trainer=True)
            )

            for user in users:
                if not user.email:
                    continue

                work_plan, _ = WorkPlan.objects.get_or_create(
                    user=user,
                    week_start_date=week_start
                )

                # All tasks this week (including leave tasks - they count as "covered")
                tasks_this_week = WorkPlanTask.objects.filter(
                    work_plan=work_plan,
                    date__gte=week_start,
                    date__lte=week_end
                )

                task_dates = set(tasks_this_week.values_list('date', flat=True))
                missing_days = [d for d in work_days if d not in task_dates]

                if not missing_days:
                    continue

                missing_days_str = ", ".join([d.strftime('%A %d %b') for d in missing_days])

                plan_link = f"{base_url}{reverse('work_plan_detail', kwargs={'pk': work_plan.pk})}"
                list_link = f"{base_url}{reverse('work_plan_list')}"

                message = f"""
Dear {user.get_full_name()},

MONDAY REMINDER: Missing Tasks for This Week

Week: {week_start.strftime('%d %b %Y')} - {week_end.strftime('%d %b %Y')} (Monday to Friday)

The following days have no tasks planned yet:
{missing_days_str}

Please add your tasks for these days before the 10:00 AM deadline today.

Direct link to your work plan: {plan_link}
All work plans: {list_link}

Thank you for keeping your plan up to date.

IT Operations System
                """.strip()

                subject = f"[MONDAY REMINDER] Missing Tasks for Week {week_start.strftime('%d %b %Y')}"

                if not dry_run:
                    success = send_custom_email(
                        subject=subject,
                        message=message,
                        recipient_list=[user.email]
                    )
                    if success:
                        sent_count += 1
                else:
                    self.stdout.write(
                        self.style.NOTICE(
                            f"[DRY-RUN] Would send Monday reminder to {user.email} (missing: {missing_days_str})"
                        )
                    )

        self.stdout.write(self.style.SUCCESS(f"\nReminder dispatch completed. Sent {sent_count} emails."))
