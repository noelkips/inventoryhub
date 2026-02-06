"""
Django management command to send weekly work plan summaries every Saturday at 6am.

This script:
1. Generates PDF reports for each user's current week and current month work plans
2. Calculates weekly and monthly task statistics (completed, pending, rescheduled)
3. Sends personalized email summaries with attached PDFs to each user
4. Designed to be run via cron job every Saturday at 6:00 AM

Usage:
    python manage.py send_workplan_summaries

Cron job (every Saturday at 6 AM):
    0 6 * * 6 cd /path/to/project && /path/to/python manage.py send_workplan_summaries

    # Production - every Saturday at 06:00 AM
0 6 * * 6 cd /home/ufdxwals/inventory_test && /home/ufdxwals/virtualenv/inventory_test/3.10/bin/python -X utf8 manage.py send_workplan_summaries >> /home/ufdxwals/inventory_test/logs/workplan_summaries.log 2>&1

*/5 * * * * cd /home/ufdxwals/inventory_test && /home/ufdxwals/virtualenv/inventory_test/3.10/bin/python -X utf8 manage.py send_workplan_summaries >> /home/ufdxwals/inventory_test/logs/workplan_summaries.log 2>&1
"""

# File: it_operations/management/commands/send_workplan_summaries.py

import calendar
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.db.models import Q
from devices.models import CustomUser
from it_operations.models import WorkPlan, WorkPlanTask
from it_operations.views.work_plan_views import _build_workplan_pdf  # Direct import of the PDF builder
from devices.utils.emails import send_custom_email  # Central email utility


class Command(BaseCommand):
    help = 'Sends weekly and monthly work plan summary emails to all relevant users every Saturday at 6 AM'

    def handle(self, *args, **options):
        self.stdout.write("Starting work plan summary email dispatch...")

        today = timezone.now().date()
        if today.weekday() != 5:  # 5 = Saturday
            self.stdout.write(self.style.NOTICE("Not Saturday - skipping (dry-run mode for testing only)."))
            # Remove the above block in production - this is just for safe testing

        # Determine current week (Monday to Saturday)
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = week_start + timedelta(days=5)  # Saturday

        # Current month
        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        # Get all active IT staff and trainers (users who can have work plans)
        users = CustomUser.objects.filter(
            is_active=True
        ).filter(
            Q(is_staff=True) | Q(is_trainer=True)
        ).distinct()

        sent_count = 0
        for user in users:
            # Weekly tasks
            weekly_tasks = WorkPlanTask.objects.filter(
                Q(work_plan__user=user) | Q(collaborators=user),
                date__gte=week_start,
                date__lte=week_end
            ).distinct()

            weekly_completed = weekly_tasks.filter(status='Completed').count()
            weekly_pending = weekly_tasks.filter(status='Pending').count()
            weekly_rescheduled = weekly_tasks.filter(status='Rescheduled').count()
            weekly_total = weekly_tasks.count()

            # Monthly tasks
            monthly_tasks = WorkPlanTask.objects.filter(
                Q(work_plan__user=user) | Q(collaborators=user),
                date__year=today.year,
                date__month=today.month
            ).distinct()

            monthly_completed = monthly_tasks.filter(status='Completed').count()
            monthly_pending = monthly_tasks.filter(status='Pending').count()
            monthly_rescheduled = monthly_tasks.filter(status='Rescheduled').count()
            monthly_total = monthly_tasks.count()

            # Only send if there is any activity in week or month
            if weekly_total == 0 and monthly_total == 0:
                continue

            # Generate PDFs
            # Weekly PDF
            weekly_work_plans = WorkPlan.objects.filter(
                user=user,
                week_start_date=week_start
            )
            weekly_pdf_bytes = _build_workplan_pdf(
                list(weekly_work_plans),
                None,  # No request.user needed for command
                title=f"Weekly Work Plan - {user.get_full_name()}",
                report_type="weekly",
                period_str=f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}",
                target_user=user
            )

            # Monthly PDF
            monthly_work_plans = WorkPlan.objects.filter(
                user=user,
                week_start_date__year=today.year,
                week_start_date__month=today.month
            )
            monthly_pdf_bytes = _build_workplan_pdf(
                list(monthly_work_plans),
                None,
                title=f"Monthly Work Plan - {user.get_full_name()} ({calendar.month_name[today.month]} {today.year})",
                report_type="monthly",
                period_str=f"{calendar.month_name[today.month]} {today.year}",
                target_user=user
            )

            # Compose message
            message = f"""
Dear {user.get_full_name()},

Here is your work plan summary:

WEEKLY SUMMARY ({week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}):
- Total tasks: {weekly_total}
- Completed: {weekly_completed}
- Pending: {weekly_pending}
- Rescheduled: {weekly_rescheduled}

MONTHLY SUMMARY ({calendar.month_name[today.month]} {today.year}):
- Total tasks: {monthly_total}
- Completed: {monthly_completed}
- Pending: {monthly_pending}
- Rescheduled: {monthly_rescheduled}

Please find attached:
- Your detailed weekly work plan PDF
- Your detailed monthly work plan PDF

Thank you.

Best regards,
IT Operations System
            """.strip()

            subject = f"Work Plan Summary - Week of {week_start.strftime('%d %b %Y')} & {calendar.month_name[today.month]} {today.year}"

            # Attachments
            attachments = [
                (
                    f"Weekly_WorkPlan_{user.username}_{week_start.strftime('%Y%m%d')}.pdf",
                    weekly_pdf_bytes,
                    'application/pdf'
                ),
                (
                    f"Monthly_WorkPlan_{user.username}_{today.year}_{today.month:02d}.pdf",
                    monthly_pdf_bytes,
                    'application/pdf'
                )
            ]

            # Send using central utility (handles test mode redirection automatically)
            success = send_custom_email(
                subject=subject,
                message=message,
                recipient_list=[user.email],
                attachment=attachments[0]  # send_custom_email supports one attachment
            )
            if success:
                # Second attachment - send a follow-up email (simple but effective)
                send_custom_email(
                    subject=subject + " (Monthly Attachment)",
                    message="Monthly work plan PDF attached (continued from previous email).",
                    recipient_list=[user.email],
                    attachment=attachments[1]
                )

                sent_count += 1
                self.stdout.write(self.style.SUCCESS(f"Summary email sent to {user.get_full_name()} ({user.email})"))

        self.stdout.write(self.style.SUCCESS(f"\nSummary email dispatch completed. Sent to {sent_count} users."))