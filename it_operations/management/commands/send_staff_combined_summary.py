# it_operations/management/commands/send_staff_combined_summary.py

import os
from datetime import timedelta
from io import BytesIO
from collections import OrderedDict
from xml.sax.saxutils import escape as xml_escape

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.utils import timezone

from devices.models import CustomUser
from it_operations.models import WorkPlanTask


class Command(BaseCommand):
    help = "Sends compact combined weekly work plan PDF to Gerald, CC IT"

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

    MOHI_GREEN = "#0B7A3B"
    MOHI_GRAY = "#6B7280"
    MOHI_BORDER = "#D1D5DB"
    MOHI_ROW_ALT = "#F9FAFB"
    MOHI_HEADER_BG = "#E9F7EF"

    def _get_to_and_cc(self):
        return ["gerald.kamande@mohiafrica.org"], ["it@mohiafrica.org"]

    def _safe(self, v):
        return "" if v is None else str(v).strip()

    def _e(self, v):
        """Escape user text for ReportLab Paragraph markup, preserve newlines."""
        txt = self._safe(v)
        txt = xml_escape(txt)
        txt = txt.replace("\r\n", "\n").replace("\r", "\n")
        txt = txt.replace("\n", "<br/>")
        return txt

    def _build_pdf(self, week_start, week_end, tasks_qs):
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm, cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=8 * mm,
            rightMargin=8 * mm,
            topMargin=8 * mm,
            bottomMargin=8 * mm,
        )

        styles = getSampleStyleSheet()

        ReportTitle = ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontSize=15,
            textColor=colors.HexColor(self.MOHI_GREEN),
            spaceAfter=4,
        )

        SubHeader = ParagraphStyle(
            "SubHeader",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor(self.MOHI_GRAY),
        )

        DayHeader = ParagraphStyle(
            "DayHeader",
            parent=styles["Heading2"],
            fontSize=11,
            textColor=colors.HexColor(self.MOHI_GREEN),
            spaceBefore=8,
            spaceAfter=6,
        )

        # Table header cells
        TH = ParagraphStyle(
            "TH",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=10,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor(self.MOHI_GREEN),
        )

        # Body cell base styles
        PeopleStyle = ParagraphStyle(
            "PeopleStyle",
            parent=styles["Normal"],
            fontSize=8.4,
            leading=10,
        )

        TaskStyle = ParagraphStyle(
            "TaskStyle",
            parent=styles["Normal"],
            fontSize=9.0,
            leading=11,
            fontName="Helvetica-Bold",
        )

        DetailsStyle = ParagraphStyle(
            "DetailsStyle",
            parent=styles["Normal"],
            fontSize=7.6,
            leading=9.4,
        )

        StatusStyle = ParagraphStyle(
            "StatusStyle",
            parent=styles["Normal"],
            fontSize=8.2,
            leading=10,
            fontName="Helvetica-Bold",
        )

        def P(html, style):
            return Paragraph(html, style)

        story = []

        # ✅ HEADER IMAGE (exact structure you requested)
        header_img_path = os.path.join(settings.BASE_DIR, "static", "images", "document_title_1.png")
        if os.path.exists(header_img_path):
            header_img = Image(header_img_path, width=19.5 * cm, height=1.4 * cm)
            header_img.hAlign = "CENTER"
            story.append(header_img)
            story.append(Spacer(1, 0.3 * cm))

        story.append(P("IT Department – Weekly Work Plan Report", ReportTitle))
        story.append(Spacer(1, 0.3 * cm))
        story.append(P(f"{week_start.strftime('%d %b %Y')} - {week_end.strftime('%d %b %Y')}", SubHeader))
        story.append(Spacer(1, 0.3 * cm))

        # Prepare days
        day_map = OrderedDict()
        d = week_start
        while d <= week_end:
            day_map[d] = []
            d += timedelta(days=1)

        tasks = (
            tasks_qs.select_related("work_plan", "work_plan__user", "centre", "department")
            .prefetch_related("collaborators")
            .order_by("date", "work_plan__user__username")
        )

        for t in tasks:
            if t.date in day_map:
                day_map[t.date].append(t)

        for day, day_tasks in day_map.items():
            story.append(P(day.strftime("%A (%d %b %Y)"), DayHeader))

            if not day_tasks:
                story.append(P("No tasks.", SubHeader))
                story.append(Spacer(1, 6))
                continue

            table_data = [
                [
                    P("People", TH),
                    P("Task", TH),
                    P("Details", TH),
                    P("Status", TH),
                ]
            ]

            for t in day_tasks:
                owner = getattr(getattr(t, "work_plan", None), "user", None)
                owner_name = (owner.get_full_name() or owner.username) if owner else "N/A"

                collab_names = []
                for u in t.collaborators.all():
                    nm = (u.get_full_name() or u.username or "").strip()
                    if nm and nm != owner_name:
                        collab_names.append(nm)
                collaborators = ", ".join(collab_names)

                # ✅ People cell: owner bold, collaborators muted next line
                people_html = f"<b>{self._e(owner_name)}</b>"
                if collaborators:
                    people_html += f"<br/><font color='{self.MOHI_GRAY}'>{self._e(collaborators)}</font>"
                people_cell = P(people_html, PeopleStyle)

                # ✅ Task cell: task main + centre/department muted on next line
                task_name = self._safe(getattr(t, "task_name", "")) or self._safe(getattr(t, "title", "")) or "Task"
                centre = self._safe(getattr(getattr(t, "centre", None), "name", "")) or "N/A"
                dept = self._safe(getattr(getattr(t, "department", None), "name", "")) or "N/A"

                task_html = (
                    f"{self._e(task_name)}<br/>"
                    f"<font color='{self.MOHI_GRAY}'><i>{self._e(centre)} • {self._e(dept)}</i></font>"
                )
                task_cell = P(task_html, TaskStyle)

                # ✅ Details cell: only show non-empty (escaped)
                details_lines = []
                other_parties = getattr(t, "other_parties", "")
                resources_needed = getattr(t, "resources_needed", "")
                target = getattr(t, "target", "")
                comments = getattr(t, "comments", "")
                reschedule_reason = getattr(t, "reschedule_reason", "")

                if self._safe(other_parties):
                    details_lines.append(f"<b>Other parties:</b> {self._e(other_parties)}")
                if self._safe(resources_needed):
                    details_lines.append(f"<b>Resources:</b> {self._e(resources_needed)}")
                if self._safe(target):
                    details_lines.append(f"<b>Target:</b> {self._e(target)}")
                if self._safe(comments):
                    details_lines.append(f"<b>Comments:</b> {self._e(comments)}")
                if self._safe(reschedule_reason):
                    details_lines.append(f"<b>Reschedule reason:</b> {self._e(reschedule_reason)}")

                details_html = "<br/>".join(details_lines) if details_lines else f"<font color='{self.MOHI_GRAY}'>—</font>"
                details_cell = P(details_html, DetailsStyle)

                status = self._safe(getattr(t, "status", "")) or "Pending"
                status_cell = P(self._e(status), StatusStyle)

                table_data.append([people_cell, task_cell, details_cell, status_cell])

            table = Table(
                table_data,
                colWidths=[70 * mm, 90 * mm, 105 * mm, 25 * mm],
                repeatRows=1,
            )

            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(self.MOHI_HEADER_BG)),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor(self.MOHI_BORDER)),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(self.MOHI_ROW_ALT)]),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )

            story.append(table)
            story.append(Spacer(1, 10))

        doc.build(story)
        return buffer.getvalue()

    def handle(self, *args, **options):
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=5)

        users_qs = CustomUser.objects.filter(is_active=True).filter(
            Q(username__in=self.ORDERED_USERNAMES) | Q(email__in=self.ALLOWED_EMAILS)
        ).distinct()

        users_by_username = {u.username: u for u in users_qs}
        allowed_users = [users_by_username[u] for u in self.ORDERED_USERNAMES if u in users_by_username]

        if not allowed_users:
            self.stdout.write("No users found.")
            return

        weekly_tasks_qs = WorkPlanTask.objects.filter(
            Q(work_plan__user__in=allowed_users) | Q(collaborators__in=allowed_users),
            date__gte=week_start,
            date__lte=week_end,
        ).distinct()

        weekly_total = weekly_tasks_qs.count()
        if weekly_total == 0:
            self.stdout.write("No weekly tasks.")
            return

        weekly_completed = weekly_tasks_qs.filter(status="Completed").count()
        weekly_pending = weekly_tasks_qs.filter(status="Pending").count()
        weekly_rescheduled = weekly_tasks_qs.filter(status="Rescheduled").count()

        pdf_bytes = self._build_pdf(week_start, week_end, weekly_tasks_qs)

        subject = f"Work Plan Summary - Week of {week_start.strftime('%d %b %Y')}"
        to_list, cc_list = self._get_to_and_cc()

        body = (
            "Dear Gerald,\n\n"
            "Here is the weekly work plan summary for the whole IT team. Full task details are in the attached PDF.\n\n"
            f"WEEKLY SUMMARY ({week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}):\n"
            f"- Total tasks: {weekly_total}\n"
            f"- Completed: {weekly_completed}\n"
            f"- Pending: {weekly_pending}\n"
            f"- Rescheduled: {weekly_rescheduled}\n\n"
            "Best regards,\n"
            "IT Operations System\n"
        )

        # Debug/SQLite: print to console only
        if settings.DEBUG or (settings.DATABASES.get("default", {}).get("ENGINE") == "django.db.backends.sqlite3"):
            self.stdout.write("DEBUG/SQLITE mode: email not sent.")
            self.stdout.write(f"TO: {to_list} | CC: {cc_list}")
            self.stdout.write(body)
            self.stdout.write(f"PDF bytes: {len(pdf_bytes)}")
            return

        email = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=to_list,
            cc=cc_list,
        )

        email.attach(
            f"Weekly_WorkPlan_{week_start.strftime('%Y%m%d')}.pdf",
            pdf_bytes,
            "application/pdf",
        )

        email.send(fail_silently=False)
        self.stdout.write("Summary sent successfully.")