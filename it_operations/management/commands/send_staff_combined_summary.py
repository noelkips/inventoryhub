# it_operations/management/commands/send_staff_combined_summary.py

"""
Send compact weekly workplan summary to Gerald (TO) and CC IT.

- ONE compact PDF attachment grouped by DAY (Mon–Sat)
- Table per day: Owner | Tasks
- Email body contains quick summaries; details are in PDF

Usage:
  python manage.py send_staff_combined_summary

Cron (every 2 minutes):
*/2 * * * * cd /home/ufdxwals/inventoryhub && /home/ufdxwals/virtualenv/inventoryhub/3.10/bin/python -X utf8 manage.py send_staff_combined_summary >> /home/ufdxwals/inventoryhub/logs/staff_combined_summary.log 2>&1
"""

import calendar
from datetime import timedelta
from io import BytesIO
from collections import defaultdict, OrderedDict

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.utils import timezone

from devices.models import CustomUser
from it_operations.models import WorkPlanTask


class Command(BaseCommand):
    help = "Sends compact combined weekly work plan summary PDF to Gerald, CC IT"

    # ✅ Explicit allow-list (order optional now; PDF is grouped by DAY)
    ORDERED_USERNAMES = [
        "glen.osano",
        "santana.macharia",
        "john.mwangi",
        "sylvia.wanjiru",
        "samuel.kamande",
        "noel.langat",
        "ezra.ndonga",
    ]

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
        # ✅ As you requested
        to_email = "noel.langat@mohiafrica.org"
        cc_email = "itinventory@mohiafrica.org"
        return [to_email], [cc_email]

    def _build_compact_weekly_pdf(self, *, week_start, week_end, users, tasks_qs) -> bytes:
        """
        Compact PDF grouped by day:
          - Day heading
          - Table: Owner | Tasks (compressed)
        """
        # ReportLab imports here to keep command import-safe
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=10 * mm,
            rightMargin=10 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
            title="IT Staff Weekly Work Plan Summary",
        )

        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        h_style = ParagraphStyle(
            "DayHeading",
            parent=styles["Heading2"],
            fontSize=12,
            spaceBefore=8,
            spaceAfter=6,
        )
        small_style = ParagraphStyle(
            "Small",
            parent=styles["Normal"],
            fontSize=9,
            leading=11,
        )
        tiny_style = ParagraphStyle(
            "Tiny",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
        )

        elements = []
        elements.append(Paragraph("IT Staff Weekly Work Plan Summary", title_style))
        elements.append(Paragraph(f"Week: {week_start.strftime('%d %b %Y')} - {week_end.strftime('%d %b %Y')}", small_style))
        elements.append(Spacer(1, 6))

        # Map user id -> display name (stable)
        user_name = {u.id: (u.get_full_name() or u.username) for u in users}

        # Build: day -> owner_id -> list of task strings
        day_owner_tasks = OrderedDict()
        cur = week_start
        while cur <= week_end:
            day_owner_tasks[cur] = defaultdict(list)
            cur += timedelta(days=1)

        # Pull minimal task fields
        tasks = tasks_qs.select_related("work_plan", "work_plan__user").prefetch_related("collaborators")

        for t in tasks:
            day = t.date
            if day not in day_owner_tasks:
                continue

            owner = getattr(t.work_plan, "user", None)
            if not owner:
                continue

            owner_id = owner.id
            # compressed task line: "Task name (Status)"
            # try common fields gracefully
            task_title = getattr(t, "title", None) or getattr(t, "name", None) or getattr(t, "task", None) or "Task"
            status = getattr(t, "status", "") or ""
            status_txt = f" ({status})" if status else ""
            line = f"• {task_title}{status_txt}"

            day_owner_tasks[day][owner_id].append(line)

        # Build PDF sections per day
        for day, owners_map in day_owner_tasks.items():
            day_label = day.strftime("%A (%d %b %Y)")
            elements.append(Paragraph(day_label, h_style))

            if not owners_map:
                elements.append(Paragraph("No tasks.", tiny_style))
                elements.append(Spacer(1, 6))
                continue

            # Table rows
            data = [["Owner", "Tasks"]]
            for owner_id, lines in owners_map.items():
                owner_display = user_name.get(owner_id, "Unknown")
                # compress to fewer lines by joining with <br/>
                tasks_html = "<br/>".join(lines)
                data.append([
                    Paragraph(owner_display, small_style),
                    Paragraph(tasks_html, tiny_style),
                ])

            tbl = Table(data, colWidths=[55 * mm, 215 * mm])  # compact: owner small, tasks wide
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            elements.append(tbl)
            elements.append(Spacer(1, 8))

        doc.build(elements)
        return buffer.getvalue()

    def handle(self, *args, **options):
        self.stdout.write("📩 Sending compact weekly summary (grouped by day)...")

        today = timezone.now().date()

        # Week (Mon–Sat)
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=5)

        # allow-listed users
        users_qs = CustomUser.objects.filter(is_active=True).filter(
            Q(username__in=self.ORDERED_USERNAMES) | Q(email__in=self.ALLOWED_EMAILS)
        ).distinct()

        users_by_username = {u.username: u for u in users_qs}
        allowed_users = [users_by_username[u] for u in self.ORDERED_USERNAMES if u in users_by_username]

        if not allowed_users:
            self.stdout.write(self.style.WARNING("⚠️ No allow-listed users found. Skipping."))
            return

        # Weekly tasks (owned OR collaborator) within week
        weekly_tasks_qs = WorkPlanTask.objects.filter(
            Q(work_plan__user__in=allowed_users) | Q(collaborators__in=allowed_users),
            date__gte=week_start,
            date__lte=week_end,
        ).distinct()

        weekly_total = weekly_tasks_qs.count()
        weekly_completed = weekly_tasks_qs.filter(status="Completed").count()
        weekly_pending = weekly_tasks_qs.filter(status="Pending").count()
        weekly_rescheduled = weekly_tasks_qs.filter(status="Rescheduled").count()

        if weekly_total == 0:
            self.stdout.write("ℹ️ No weekly activity detected. Skipping email.")
            return

        # Build compact PDF (weekly only, compact)
        pdf_bytes = self._build_compact_weekly_pdf(
            week_start=week_start,
            week_end=week_end,
            users=allowed_users,
            tasks_qs=weekly_tasks_qs,
        )

        # Email
        subject = f"IT Weekly Work Plan Summary - {week_start.strftime('%d %b')} to {week_end.strftime('%d %b %Y')}"

        to_list, cc_list = self._get_to_and_cc()

        body = (
            "Dear Gerald,\n\n"
            "Kindly find the weekly work plan summary below. Full task details are attached in the PDF.\n\n"
            f"Week: {week_start.strftime('%d %b %Y')} - {week_end.strftime('%d %b %Y')}\n"
            f"Total Tasks: {weekly_total}\n"
            f"Completed: {weekly_completed}\n"
            f"Pending: {weekly_pending}\n"
            f"Rescheduled: {weekly_rescheduled}\n\n"
            "Regards,\n"
            "IT Operations System\n"
        )

        # DEBUG/SQLite -> console only
        if settings.DEBUG or (settings.DATABASES.get("default", {}).get("ENGINE") == "django.db.backends.sqlite3"):
            self.stdout.write("🧪 DEBUG/SQLITE mode: Email not sent.")
            self.stdout.write(f"TO: {to_list} | CC: {cc_list}")
            self.stdout.write(body)
            self.stdout.write(f"(PDF bytes length: {len(pdf_bytes)})")
            return

        email = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=to_list,
            cc=cc_list,
        )

        filename = f"IT_Weekly_WorkPlan_{week_start.strftime('%Y%m%d')}_{week_end.strftime('%Y%m%d')}.pdf"
        email.attach(filename, pdf_bytes, "application/pdf")

        email.send(fail_silently=False)
        self.stdout.write(self.style.SUCCESS("✅ Sent to Gerald (CC IT) with compact PDF attached"))