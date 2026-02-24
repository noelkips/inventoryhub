"""
Send combined (grouped-by-user) workplan summaries to Gerald, CC IT.

- ONE PDF attachment, grouped by users (Glen first).
- Email body contains quick summaries; PDF contains detailed plans.

Usage:
  python manage.py send_staff_combined_summary

Cron (every 2 minutes):
*/2 * * * * cd /home/ufdxwals/inventoryhub && /home/ufdxwals/virtualenv/inventoryhub/3.10/bin/python -X utf8 manage.py send_staff_combined_summary >> /home/ufdxwals/inventoryhub/logs/staff_combined_summary.log 2>&1
"""

import os
import calendar
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.utils import timezone

from devices.models import CustomUser
from it_operations.models import WorkPlan, WorkPlanTask
from it_operations.views.work_plan_views import _build_workplan_pdf  # reuse your PDF builder


class Command(BaseCommand):
    help = "Sends combined work plan summary (grouped by user) to Gerald, CC IT"

    # ✅ Order matters: Glen first, then others
    ORDERED_USERNAMES = [
        "glen.osano",
        "santana.macharia",
        "john.mwangi",
        "sylvia.wanjiru",
        "samuel.kamande",
        "noel.langat",
        "ezra.ndonga",
    ]

    # (Optional safety) allow emails too
    ALLOWED_EMAILS = [
        "santana.macharia@mohiafrica.org",
        "john.mwangi@mohiafrica.org",
        "sylvia.wanjiru@mohiafrica.org",
        "glen.osano@mohiafrica.org",
        "samuel.kamande@mohiafrica.org",
        "noel.langat@mohiafrica.org",
        "ezra.ndonga@mohiafrica.org",
    ]

    def _get_to_and_cc(self):
        """
        TO: Gerald (from env var), fallback to IT
        CC: IT
        """
        to_email = "noel.langat@mohiafrica.org"
        cc_email = "itinventory@mohiafrica.org"
        return [to_email], [cc_email]

    def _merge_pdfs(self, pdf_bytes_list):
        """
        Merge multiple PDF byte strings into one PDF bytes.
        Requires PyPDF2.
        """
        try:
            from PyPDF2 import PdfMerger
        except Exception as e:
            raise RuntimeError(
                "PyPDF2 is required to merge PDFs. Install: pip install PyPDF2"
            ) from e

        merger = PdfMerger()
        for b in pdf_bytes_list:
            if not b:
                continue
            merger.append(BytesIO(b))

        out = BytesIO()
        merger.write(out)
        merger.close()
        return out.getvalue()

    def handle(self, *args, **options):
        self.stdout.write("🚀 Sending grouped combined summary (Glen first)...")

        today = timezone.now().date()

        # Week (Mon–Sat)
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=5)

        # Month label
        month_label = f"{calendar.month_name[today.month]} {today.year}"

        # Pull only allow-listed users
        users_qs = CustomUser.objects.filter(is_active=True).filter(
            Q(username__in=self.ORDERED_USERNAMES) | Q(email__in=self.ALLOWED_EMAILS)
        ).distinct()

        users_by_username = {u.username: u for u in users_qs}
        ordered_users = [users_by_username[u] for u in self.ORDERED_USERNAMES if u in users_by_username]

        if not ordered_users:
            self.stdout.write(self.style.WARNING("⚠️ No allow-listed users found. Skipping."))
            return

        # Build per-user PDFs (weekly + monthly) then merge into ONE, in the right order
        per_user_combined_pdfs = []
        summary_lines = []

        total_week_all = 0
        total_month_all = 0

        for user in ordered_users:
            # Weekly tasks stats
            weekly_tasks = WorkPlanTask.objects.filter(
                Q(work_plan__user=user) | Q(collaborators=user),
                date__gte=week_start,
                date__lte=week_end,
            ).distinct()

            w_total = weekly_tasks.count()
            w_completed = weekly_tasks.filter(status="Completed").count()
            w_pending = weekly_tasks.filter(status="Pending").count()
            w_rescheduled = weekly_tasks.filter(status="Rescheduled").count()

            # Monthly tasks stats
            monthly_tasks = WorkPlanTask.objects.filter(
                Q(work_plan__user=user) | Q(collaborators=user),
                date__year=today.year,
                date__month=today.month,
            ).distinct()

            m_total = monthly_tasks.count()
            m_completed = monthly_tasks.filter(status="Completed").count()
            m_pending = monthly_tasks.filter(status="Pending").count()
            m_rescheduled = monthly_tasks.filter(status="Rescheduled").count()

            total_week_all += w_total
            total_month_all += m_total

            summary_lines.append(
    (
        f"{user.get_full_name()}:\n"
        f"  Weekly Tasks: {w_total}\n"
        f"    - Completed: {w_completed}\n"
        f"    - Pending: {w_pending}\n"
        f"    - Rescheduled: {w_rescheduled}\n"
        f"  Monthly Tasks: {m_total}\n"
        f"    - Completed: {m_completed}\n"
        f"    - Pending: {m_pending}\n"
        f"    - Rescheduled: {m_rescheduled}\n"
    )
)

            # Weekly plans PDF (for that user)
            weekly_work_plans = WorkPlan.objects.filter(user=user, week_start_date=week_start)
            weekly_pdf = _build_workplan_pdf(
                list(weekly_work_plans),
                None,
                title=f"{user.get_full_name()} - Weekly Work Plan",
                report_type="weekly",
                period_str=f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}",
                target_user=user,
            )

            # Monthly plans PDF (for that user)
            monthly_work_plans = WorkPlan.objects.filter(
                user=user,
                week_start_date__year=today.year,
                week_start_date__month=today.month,
            )
            monthly_pdf = _build_workplan_pdf(
                list(monthly_work_plans),
                None,
                title=f"{user.get_full_name()} - Monthly Work Plan ({month_label})",
                report_type="monthly",
                period_str=month_label,
                target_user=user,
            )

            # Merge weekly+monthly for this user (keeps user separated)
            user_combined_pdf = self._merge_pdfs([weekly_pdf, monthly_pdf])
            per_user_combined_pdfs.append(user_combined_pdf)

        # If absolutely no activity, skip
        if total_week_all == 0 and total_month_all == 0:
            self.stdout.write("ℹ️ No activity found. Skipping email.")
            return

        # Final PDF: Glen section first, then others (each already grouped)
        final_pdf = self._merge_pdfs(per_user_combined_pdfs)

        # Email (short summaries, details in PDF)
        subject = f"IT Staff Work Plan Summary (Grouped PDF) - {timezone.now().strftime('%d %b %Y %H:%M')}"
        to_list, cc_list = self._get_to_and_cc()

        body = (
            "Dear Gerald,\n\n"
            "Kindly find the IT staff work plan summaries below. Full details are attached in the grouped PDF "
            "(Glen first, followed by the rest).\n\n"
            f"WEEK ({week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}): Total tasks = {total_week_all}\n"
            f"MONTH ({month_label}): Total tasks = {total_month_all}\n\n"
            "Per-user summary:\n"
            + "\n".join(summary_lines)
            + "\n\n"
            "Regards,\n"
            "IT Operations System\n"
        )

        # DEBUG: print instead of sending
        if settings.DEBUG or (settings.DATABASES.get("default", {}).get("ENGINE") == "django.db.backends.sqlite3"):
            self.stdout.write("🧪 DEBUG/SQLITE mode: Email not sent.")
            self.stdout.write(f"TO: {to_list} | CC: {cc_list}")
            self.stdout.write(body)
            self.stdout.write(f"(PDF bytes length: {len(final_pdf)})")
            return

        email = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=to_list,
            cc=cc_list,
        )

        filename = f"IT_Staff_WorkPlan_Grouped_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
        email.attach(filename, final_pdf, "application/pdf")

        email.send(fail_silently=False)
        self.stdout.write(self.style.SUCCESS("✅ Sent to Gerald (CC it@mohiafrica) with grouped PDF attached"))