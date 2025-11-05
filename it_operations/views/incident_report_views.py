# ... existing imports
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.db.models import Q
from django.apps import apps

# --- PDF Generation Imports ---
import io
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, ListFlowable, ListItem 
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
# ... other imports
from django.conf import settings 

import os
from ..models import IncidentReport

User = get_user_model()


# ============ LIST HELPER FOR PDF (FIXED) ============

def _format_text_as_list(text, style):
    """
    Converts newline-separated text into a ReportLab ListFlowable. 
    Returns a list containing the Paragraph or ListFlowable object(s).
    """
    if not text:
        # Returns a list containing one Paragraph flowable
        return [Paragraph("N/A", style)]
    
    # Split the text by newline and filter out empty lines, trimming whitespace
    items = [line.strip() for line in text.splitlines() if line.strip()]

    if not items:
        # Returns a list containing one Paragraph flowable
        return [Paragraph("N/A", style)]

    # Create ListItems for each line of content
    list_items = [ListItem(Paragraph(item, style), leftIndent=0.7*cm, bulletIndent=0.3*cm) for item in items]
    
    # Create the ListFlowable object
    list_flowable = ListFlowable(
        list_items,
        bulletType='bullet',
        start=None, 
        bulletFontName='Helvetica', 
        bulletFontSize=10,
        spaceAfter=0.1*cm,
    )
    
    # FIX: Wrap the single ListFlowable object in a list so story.extend() works.
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
    # Renders using the updated report_detail.html
    return render(request, 'it_operations/incident_report/report_detail.html', context)


@login_required
def incident_report_create(request):
    """Create a new incident report"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to create incident reports.")
        return redirect('dashboard')

    if request.method == 'POST':
        try:
            report = IncidentReport(
                reported_by=request.user, # Set the logged-in user
                reporter_title_role=request.POST.get('reporter_title_role'),
                incident_type=request.POST.get('incident_type'),
                date_of_incident=request.POST.get('date_of_incident'),
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
            
            # Handle Collaborators M2M
            collaborator_ids = request.POST.getlist('collaborators')
            if collaborator_ids:
                report.collaborators.set(collaborator_ids)
            
            messages.success(request, 'Incident Report created successfully!')
            return redirect('incident_report_detail', pk=report.pk)
        except Exception as e:
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
            report.reporter_title_role = request.POST.get('reporter_title_role')
            report.incident_type = request.POST.get('incident_type')
            report.date_of_incident = request.POST.get('date_of_incident')
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
            
            # Handle Collaborators M2M
            collaborator_ids = request.POST.getlist('collaborators')
            report.collaborators.set(collaborator_ids)
            
            messages.success(request, 'Incident Report updated successfully!')
            return redirect('incident_report_detail', pk=report.pk)
        except Exception as e:
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
    """Delete confirmation for incident report"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to delete reports.")
        return redirect('dashboard')
        
    report = get_object_or_404(IncidentReport, pk=pk)
    
    if request.method == 'POST':
        report.delete()
        messages.success(request, 'Incident Report deleted successfully!')
        return redirect('incident_report_list')
    
    context = {'report': report}
    return render(request, 'it_operations/incident_report/report_confirm_delete.html', context)

# Define Custom Colors based on your theme
DARK_BLUE = colors.HexColor('#143C50') 
ACCENT_TEAL = colors.HexColor('#288CC8') # Your accent color
LIGHT_GRAY = colors.HexColor('#F5F5F5')
BORDER_GRAY = colors.HexColor('#CCCCCC')


def _build_incident_pdf(report):
    buffer = io.BytesIO()
    
    # Use SimpleDocTemplate for a flowable structure
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
    
    # --- Custom Paragraph Styles ---
    # FIX: Renamed 'Title' to 'ReportTitle' to avoid KeyError, as 'Title' already exists
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

    # NEW STYLE FOR LIST TEXT
    styles.add(ParagraphStyle(
        name='ListText', 
        parent=styles['Data'], 
        leftIndent=0,
        spaceBefore=0,
        spaceAfter=0.05 * cm
    ))

    logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'document_title_1.png') 
    
    try:
        # Create an Image flowable
        logo = Image(logo_path, width=16.5*cm, height=1.4*cm) 
        logo.hAlign = 'CENTER' # Center the image
        story.append(logo)
        story.append(Spacer(1, 0.5*cm)) # Add some space below the logo
    except FileNotFoundError:
        # Handle the case where the logo file is not found
        pass 
    
    # --- 1. Title Block ---
    story.append(Paragraph("IT Department – Incident Report", styles['ReportTitle']))
    
    # --- 2. Header Table (Reported By, Date, Incident No.) ---
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

    # --- 3. Incident Information Section ---
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

    # --- 4. Description Section ---
    story.append(Paragraph("Incident Description", styles['SectionHeading']))
    desc_data = [[Paragraph(report.description or "No description provided.", styles['Data'])]]
    desc_table = Table(desc_data, colWidths=[17 * cm])
    desc_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ('PADDING', (0, 0), (-1, -1), 5)
    ]))
    story.append(desc_table)

    # --- 5. Involved Parties & Witnesses Section (FIXED to use extend correctly) ---
    story.append(Paragraph("Parties Involved & Witnesses", styles['SectionHeading']))
    
    story.append(Paragraph("<b>Parties Involved:</b>", styles['Data']))
    story.extend(_format_text_as_list(report.parties_involved, styles['ListText']))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("<b>Witnesses:</b>", styles['Data']))
    story.extend(_format_text_as_list(report.witnesses, styles['ListText']))
    story.append(Spacer(1, 0.2*cm))
    
    # --- 6. Actions and Follow-up Section (FIXED to use extend correctly) ---
    story.append(Paragraph("Actions and Follow-up", styles['SectionHeading']))

    # Immediate Actions (as list)
    story.append(Paragraph("<b>Immediate Actions Taken:</b>", styles['Data']))
    story.extend(_format_text_as_list(report.immediate_actions_taken, styles['ListText']))
    story.append(Spacer(1, 0.2*cm))

    # Reported To (as single-row table)
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


    # Follow-up Actions (as list)
    story.append(Paragraph("<b>Follow-up Actions Required:</b>", styles['Data']))
    story.extend(_format_text_as_list(report.follow_up_actions_required, styles['ListText']))
    story.append(Spacer(1, 0.2*cm))

    # --- 7. Additional Notes Section (FIXED to use extend correctly) ---
    story.append(Paragraph("Additional Notes", styles['SectionHeading']))
    story.extend(_format_text_as_list(report.additional_notes, styles['ListText']))
    story.append(Spacer(1, 0.2*cm))

    doc.build(story)
    
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

@login_required
def download_incident_report_pdf(request, pk):
    """Download the incident report as a PDF."""
    report = get_object_or_404(IncidentReport, pk=pk)
    
    # Permission check: Only the reported_by user or a superuser can download
    if request.user != report.reported_by and not request.user.is_superuser:
        messages.error(request, "You do not have permission to download this report.")
        return redirect('incident_report_detail', pk=pk)
        
    pdf_content = _build_incident_pdf(report)
    
    # Create the HTTP response
    response = HttpResponse(pdf_content, content_type='application/pdf')
    
    # Set the filename for the download
    filename = f"Incident_Report_{report.incident_number.replace('/', '_')}_{report.date_of_report.strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response