# --- Django Imports ---
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.db.models import Q
from django.apps import apps
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponse

# --- DateTime Imports ---
from datetime import datetime

# --- ReportLab Imports for PDF Generation ---
import io
import os
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, 
    TableStyle, Image, ListFlowable, ListItem
)

# --- Project Imports ---
from devices.utils import send_custom_email
from ..models import IncidentReport

# --- Global Variables ---
User = get_user_model()

# --- Custom Colors ---
DARK_BLUE = colors.HexColor('#143C50')
ACCENT_TEAL = colors.HexColor('#288CC8')
LIGHT_GRAY = colors.HexColor('#F5F5F5')
BORDER_GRAY = colors.HexColor('#CCCCCC')

# ============ LIST HELPER FOR PDF ============
def _format_text_as_list(text, style):
    """
    Converts newline-separated text into a ReportLab ListFlowable.
    Returns a list containing the Paragraph or ListFlowable object(s).
    """
    if not text:
        return [Paragraph("N/A", style)]
    
    items = [line.strip() for line in text.splitlines() if line.strip()]
    if not items:
        return [Paragraph("N/A", style)]

    list_items = [ListItem(Paragraph(item, style), leftIndent=0.7*cm, bulletIndent=0.3*cm) for item in items]
    list_flowable = ListFlowable(
        list_items,
        bulletType='bullet',
        start=None,
        bulletFontName='Helvetica',
        bulletFontSize=10,
        spaceAfter=0.1*cm,
    )
    return [list_flowable]

# ============ INCIDENT REPORT VIEWS ============

@login_required
def incident_report_list(request):
    """Display all incident reports"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to access Incident Reports.")
        return redirect('dashboard')
    
    IncidentReportModel = apps.get_model('it_operations', 'IncidentReport')
    reports = IncidentReportModel.objects.all()
    
    search = request.GET.get('search')
    if search:
        reports = reports.filter(
            Q(incident_number__icontains=search) |
            Q(incident_type__icontains=search) |
            Q(location__icontains=search) |
            Q(description__icontains=search)
        )
    
    paginator = Paginator(reports, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'reports': page_obj.object_list,
    }
    return render(request, 'it_operations/incident_report/report_list.html', context)

@login_required
def incident_report_detail(request, pk):
    """Display a single incident report"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to access this.")
        return redirect('dashboard')
    
    report = get_object_or_404(IncidentReport, pk=pk)
    context = {'report': report}
    return render(request, 'it_operations/incident_report/report_detail.html', context)

@login_required
def incident_report_create(request):
    """Create a new incident report"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to create incident reports.")
        return redirect('dashboard')

    if request.method == 'POST':
        try:
            date_incident_str = request.POST.get('date_of_incident')
            aware_date_incident = None
            if date_incident_str:
                try:
                    naive_dt = datetime.strptime(date_incident_str, '%Y-%m-%dT%H:%M')
                    aware_date_incident = timezone.make_aware(naive_dt, timezone.get_current_timezone())
                except ValueError:
                    messages.error(request, "Invalid date format. Date was not saved.")
            
            report = IncidentReport(
                reported_by=request.user,
                reporter_title_role=request.POST.get('reporter_title_role'),
                incident_type=request.POST.get('incident_type'),
                date_of_incident=aware_date_incident,
                location=request.POST.get('location'),
                specific_area=request.POST.get('specific_area'),
                description=request.POST.get('description'),
                parties_involved=request.POST.get('parties_involved'),
                witnesses=request.POST.get('witnesses'),
                immediate_actions_taken=request.POST.get('immediate_actions_taken'),
                reported_to=request.POST.get('reported_to'),
                follow_up_actions_required=request.POST.get('follow_up_actions_required'),
                additional_notes=request.POST.get('additional_notes')
            )
            report.save()

            collaborator_ids = request.POST.getlist('collaborators')
            if collaborator_ids:
                report.collaborators.set(collaborator_ids)

            # ================== PDF GENERATION & EMAIL SENDING ==================
            pdf_content = _build_incident_pdf(report)
            pdf_filename = f"Incident_Report_{report.incident_number.replace('/', '_')}.pdf"

            collaborator_emails = [email for email in report.collaborators.all().values_list('email', flat=True) if email]
            user_recipient_set = {request.user.email}
            user_recipient_set.update(collaborator_emails)
            user_recipient_list = [email for email in user_recipient_set if email]

            subject_user = f"Incident Report Submitted (Ref: {report.incident_number})"
            message_user = f"""
Dear {request.user.get_full_name() or request.user.username},

Your incident report (Ref: {report.incident_number}) has been successfully logged.
A copy is attached for your records.

Thank you,
IT Operations Team
""".strip()

            attachment_user = (pdf_filename, pdf_content, 'application/pdf') if user_recipient_list else None
            send_custom_email(subject_user, message_user, user_recipient_list, attachment_user)

            try:
                report_url = request.build_absolute_uri(reverse('incident_report_detail', kwargs={'pk': report.pk}))
            except:
                report_url = "Check Dashboard"

            subject_it = f"ACTION REQUIRED: New Incident - {report.incident_type} ({report.incident_number})"
            message_it = f"""
New incident report submitted by {report.reported_by.get_full_name()}.

Type: {report.incident_type}
Location: {report.location}
Link: {report_url}

Please see attached PDF.
""".strip()

            send_custom_email(
                subject_it,
                message_it,
                ["it@mohiafrica.org"],
                (pdf_filename, pdf_content, 'application/pdf')
            )

            messages.success(request, 'Incident Report created and notifications sent!')
            return redirect('incident_report_detail', pk=report.pk)

        except Exception as e:
            print(f"CRITICAL ERROR in Incident Create: {e}")
            messages.error(request, f"Error creating report: {e}")
            return redirect('incident_report_create')

    all_users = User.objects.filter(is_active=True)
    context = {
        'action': 'Create',
        'all_users': all_users,
    }
    return render(request, 'it_operations/incident_report/report_form.html', context)

@login_required
def incident_report_update(request, pk):
    """Update an existing incident report"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to update reports.")
        return redirect('dashboard')
        
    report = get_object_or_404(IncidentReport, pk=pk)
    
    if request.method == 'POST':
        try:
            date_incident_str = request.POST.get('date_of_incident')
            aware_date_incident = report.date_of_incident
            if date_incident_str:
                try:
                    naive_dt = datetime.strptime(date_incident_str, '%Y-%m-%dT%H:%M')
                    aware_date_incident = timezone.make_aware(naive_dt, timezone.get_current_timezone())
                except ValueError:
                    messages.warning(request, "Invalid date format. Keeping original date.")
            else:
                aware_date_incident = None

            report.reporter_title_role = request.POST.get('reporter_title_role')
            report.incident_type = request.POST.get('incident_type')
            report.date_of_incident = aware_date_incident
            report.location = request.POST.get('location')
            report.specific_area = request.POST.get('specific_area')
            report.description = request.POST.get('description')
            report.parties_involved = request.POST.get('parties_involved')
            report.witnesses = request.POST.get('witnesses')
            report.immediate_actions_taken = request.POST.get('immediate_actions_taken')
            report.reported_to = request.POST.get('reported_to')
            report.follow_up_actions_required = request.POST.get('follow_up_actions_required')
            report.additional_notes = request.POST.get('additional_notes')
            
            report.save()
            
            collaborator_ids = request.POST.getlist('collaborators')
            report.collaborators.set(collaborator_ids)
            
            # ================== PDF GENERATION & EMAIL SENDING ==================
            pdf_content = _build_incident_pdf(report)
            pdf_filename = f"Incident_Report_{report.incident_number.replace('/', '_')}.pdf"

            collaborator_emails = [email for email in report.collaborators.all().values_list('email', flat=True) if email]
            user_recipient_set = {report.reported_by.email}
            user_recipient_set.update(collaborator_emails)
            user_recipient_list = [email for email in user_recipient_set if email]
            
            updated_by_name = request.user.get_full_name() or request.user.username

            subject_user = f"Incident Report Updated (Ref: {report.incident_number})"
            message_user = f"""
Dear User,

The Incident Report (Ref: {report.incident_number}) has been updated by {updated_by_name}.

Please find the latest version of the report attached.

Summary of Incident:
------------------------------------------------
Incident Number:     {report.incident_number}
Incident Type:       {report.incident_type}
Date of Incident:    {report.date_of_incident.strftime('%d/%m/%Y %H:%M') if report.date_of_incident else 'Not specified'}
------------------------------------------------

Best regards,
The IT Operations Team
""".strip()

            attachment_user = (pdf_filename, pdf_content, 'application/pdf') if user_recipient_list else None
            send_custom_email(subject_user, message_user, user_recipient_list, attachment_user)

            try:
                report_url = request.build_absolute_uri(reverse('incident_report_detail', kwargs={'pk': report.pk}))
            except Exception:
                report_url = "Please log in to dashboard."

            subject_it = f"NOTICE: Incident Report Updated - {report.incident_type} ({report.incident_number})"
            message_it = f"""
An incident report has been updated by {updated_by_name} ({request.user.email}).

Report Details:
------------------------------------------------
Ref Number:          {report.incident_number}
Reported By:         {report.reported_by.get_full_name()} (Original Reporter)
Updated By:          {updated_by_name}
Incident Type:       {report.incident_type}
------------------------------------------------

View the report online:
{report_url}

Please review the attached PDF for the latest changes.
""".strip()

            send_custom_email(
                subject_it,
                message_it,
                ["it@mohiafrica.org"],
                (pdf_filename, pdf_content, 'application/pdf')
            )

            messages.success(request, 'Incident Report updated successfully and notifications sent!')
            return redirect('incident_report_detail', pk=report.pk)
        
        except Exception as e:
            print(f"CRITICAL ERROR UPDATING REPORT: {e}")
            messages.error(request, f"Error updating report: {e}")
            return redirect('incident_report_update', pk=pk)

    all_users = User.objects.filter(is_active=True)
    context = {
        'action': 'Update',
        'report': report,
        'all_users': all_users,
    }
    return render(request, 'it_operations/incident_report/report_form.html', context)

@login_required
def incident_report_delete(request, pk):
    """Delete confirmation for incident report with IT Notification"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to delete reports.")
        return redirect('dashboard')
        
    report = get_object_or_404(IncidentReport, pk=pk)
    
    if request.method == 'POST':
        try:
            pdf_content = _build_incident_pdf(report)
            pdf_filename = f"DELETED_Incident_{report.incident_number.replace('/', '_')}.pdf"

            deleted_by = request.user.get_full_name() or request.user.username
            
            subject_it = f"NOTIFICATION: Incident Report Deleted - {report.incident_number}"
            message_it = f"""
An Incident Report has been DELETED from the system.

Details of Deleted Report:
------------------------------------------------
Incident Number:     {report.incident_number}
Incident Type:       {report.incident_type}
Deleted By:          {deleted_by} ({request.user.email})
Time of Deletion:    {timezone.now().strftime('%d/%m/%Y %H:%M')}
------------------------------------------------

A copy of the report as it existed before deletion is attached to this email for archival purposes.

Thank you,
IT Operations System
            """.strip()

            send_custom_email(
                subject_it,
                message_it,
                ["it@mohiafrica.org"],
                (pdf_filename, pdf_content, 'application/pdf')
            )

        except Exception as e:
            print(f"Error sending delete notification: {e}")

        report.delete()
        messages.success(request, 'Incident Report deleted successfully! (Archival copy sent to IT)')
        return redirect('incident_report_list')
    
    context = {'report': report}
    return render(request, 'it_operations/incident_report/report_confirm_delete.html', context)

@login_required
def download_incident_report_pdf(request, pk):
    """Download the incident report as a PDF."""
    report = get_object_or_404(IncidentReport, pk=pk)
    
    if request.user != report.reported_by and not request.user.is_superuser:
        messages.error(request, "You do not have permission to download this report.")
        return redirect('incident_report_detail', pk=pk)
        
    pdf_content = _build_incident_pdf(report)
    
    response = HttpResponse(pdf_content, content_type='application/pdf')
    filename = f"Incident_Report_{report.incident_number.replace('/', '_')}_{report.date_of_report.strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

# ============ PDF GENERATION ============
def _build_incident_pdf(report):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        title=f"Incident Report {report.incident_number}"
    )

    story = []
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='ReportTitle',
        fontName='Helvetica-Bold',
        fontSize=18,
        alignment=1,
        spaceAfter=0.5 * cm,
        textColor=DARK_BLUE
    ))
    
    styles.add(ParagraphStyle(
        name='HeaderDetail',
        fontName='Helvetica',
        fontSize=10,
        spaceBefore=0,
        spaceAfter=0
    ))

    styles.add(ParagraphStyle(
        name='SectionHeading',
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=colors.white,
        backColor=ACCENT_TEAL,
        leftIndent=3,
        spaceBefore=0.4 * cm,
        spaceAfter=0.2 * cm,
        borderPadding=3
    ))
    
    styles.add(ParagraphStyle(
        name='Label',
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=DARK_BLUE,
        spaceAfter=0
    ))
    
    styles.add(ParagraphStyle(
        name='Data',
        fontName='Helvetica',
        fontSize=10,
        spaceAfter=0.2 * cm
    ))

    styles.add(ParagraphStyle(
        name='ListText',
        parent=styles['Data'],
        leftIndent=0,
        spaceBefore=0,
        spaceAfter=0.05 * cm
    ))

    logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'document_title_1.png')
    try:
        logo = Image(logo_path, width=16.5*cm, height=1.4*cm)
        logo.hAlign = 'CENTER'
        story.append(logo)
        story.append(Spacer(1, 0.5*cm))
    except FileNotFoundError:
        pass
    
    story.append(Paragraph("IT Department – Incident Report", styles['ReportTitle']))
    
    header_data = [
        [
            Paragraph("Reported By:", styles['Label']),
            Paragraph(report.reported_by.get_full_name() if report.reported_by else "N/A", styles['Data']),
            Paragraph("Date of Report:", styles['Label']),
            Paragraph(report.date_of_report.strftime("%d/%m/%Y"), styles['Data'])
        ],
        [
            Paragraph("Title / Role:", styles['Label']),
            Paragraph(report.reporter_title_role or "N/A", styles['Data']),
            Paragraph("Incident No.:", styles['Label']),
            Paragraph(report.incident_number or "N/A", styles['Data'])
        ]
    ]

    header_table = Table(header_data, colWidths=[3 * cm, 6 * cm, 3 * cm, 5 * cm])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_GRAY)
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("Incident Information", styles['SectionHeading']))

    collaborators_list = ", ".join([user.get_full_name() for user in report.collaborators.all()]) or "None"
    
    incident_data = [
        [
            Paragraph("Incident Type:", styles['Label']),
            Paragraph(report.incident_type or "N/A", styles['Data']),
            Paragraph("Date of Incident:", styles['Label']),
            Paragraph(
                report.date_of_incident.strftime("%d/%m/%Y %H:%M") if report.date_of_incident else "Not Specified",
                styles['Data']
            )
        ],
        [
            Paragraph("Location:", styles['Label']),
            Paragraph(report.location or "N/A", styles['Data']),
            Paragraph("Specific Area:", styles['Label']),
            Paragraph(report.specific_area or "N/A", styles['Data'])
        ],
        [
            Paragraph("Collaborators:", styles['Label']),
            Paragraph(collaborators_list, styles['Data']),
            Paragraph("", styles['Label']),
            Paragraph("", styles['Data'])
        ]
    ]
    
    incident_table = Table(incident_data, colWidths=[3.5 * cm, 5.5 * cm, 3.5 * cm, 4.5 * cm])
    incident_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_GRAY)
    ]))
    story.append(incident_table)

    story.append(Paragraph("Incident Description", styles['SectionHeading']))
    desc_data = [[Paragraph(report.description or "No description provided.", styles['Data'])]]
    desc_table = Table(desc_data, colWidths=[17 * cm])
    desc_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ('PADDING', (0, 0), (-1, -1), 5)
    ]))
    story.append(desc_table)

    story.append(Paragraph("Parties Involved & Witnesses", styles['SectionHeading']))
    story.append(Paragraph("<b>Parties Involved:</b>", styles['Data']))
    story.extend(_format_text_as_list(report.parties_involved, styles['ListText']))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("<b>Witnesses:</b>", styles['Data']))
    story.extend(_format_text_as_list(report.witnesses, styles['ListText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("Actions and Follow-up", styles['SectionHeading']))
    story.append(Paragraph("<b>Immediate Actions Taken:</b>", styles['Data']))
    story.extend(_format_text_as_list(report.immediate_actions_taken, styles['ListText']))
    story.append(Spacer(1, 0.2*cm))

    reported_to_data = [
        [Paragraph("<b>Reported To:</b>", styles['Label']), Paragraph(report.reported_to or "N/A", styles['Data'])]
    ]
    reported_to_table = Table(reported_to_data, colWidths=[4 * cm, 12 * cm])
    reported_to_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_GRAY)
    ]))
    story.append(reported_to_table)
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("<b>Follow-up Actions Required:</b>", styles['Data']))
    story.extend(_format_text_as_list(report.follow_up_actions_required, styles['ListText']))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("Additional Notes", styles['SectionHeading']))
    story.extend(_format_text_as_list(report.additional_notes, styles['ListText']))
    story.append(Spacer(1, 0.2*cm))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

# ============ SHELL HELPER ============
def send_incident_report_email_by_pk(pk):
    """
    Call this in shell: send_incident_report_email_by_pk(2)
    Sends email + PDF to the reporter + noellangat28@gmail.com
    """
    try:
        report = IncidentReport.objects.get(pk=pk)
    except IncidentReport.DoesNotExist:
        print(f"ERROR → No IncidentReport with PK={pk}")
        return

    try:
        pdf_content = _build_incident_pdf(report)
    except Exception as e:
        print(f"ERROR generating PDF for PK={pk}: {e}")
        return

    subject = f"Incident Report - {report.incident_number}"
    message = f"""
Hello,

Please find attached the official Incident Report that was submitted.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Incident Number     : {report.incident_number}
Incident Type       : {report.incident_type or 'N/A'}
Date of Incident    : {report.date_of_incident.strftime('%d/%m/%Y %H:%M') if report.date_of_incident else 'Not specified'}
Location            : {report.location or 'N/A'} ({report.specific_area or 'N/A'})
Reported By         : {report.reported_by.get_full_name() or report.reported_by.username}
Date of Report      : {report.date_of_report.strftime('%d/%m/%Y')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Thank you.
IT Operations System
    """.strip()

    recipients = []
    if report.reported_by.email:
        recipients.append(report.reported_by.email)
    recipients.append("noellangat28@gmail.com")

    send_custom_email(
        subject,
        message,
        recipients,
        (f"Incident_Report_{report.incident_number.replace('/', '_')}.pdf", pdf_content, "application/pdf")
    )
    print(f"SUCCESS → Email + PDF sent for PK={pk} → #{report.incident_number}")