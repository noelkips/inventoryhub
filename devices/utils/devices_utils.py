
# PDF (ReportLab)
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    Frame, PageTemplate
)
from io import BytesIO

def generate_pdf_buffer(device):
    """Generate PDF buffer for clearance form"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    elements = []

    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    normal_style = styles['Normal']
    footer_style = ParagraphStyle(
        name='FooterStyle',
        parent=normal_style,
        fontSize=10,
        alignment=1
    )
    remarks_style = ParagraphStyle(
        name='RemarksStyle',
        parent=normal_style,
        fontSize=10,
        wordWrap='CJK',
        leading=12,
        alignment=0
    )

    elements.append(Paragraph(f'Clearance Form for Device {device.serial_number} - MOHI IT Inventory', title_style))
    elements.append(Spacer(1, 12))

    data = [
        ['Field', 'Value'],
        ['Device Serial Number', device.serial_number or 'N/A'],
        ['Device Name', device.device_name or 'N/A'],
        ['Centre', device.centre.name if device.centre else 'N/A'],
        ['Department', device.department.name if device.department else 'N/A'],
        ['Status', device.status or 'N/A'],
        ['Date', device.date.strftime("%Y-%m-%d") if device.date else 'N/A'],
        ['Cleared By', device.clearances.first().cleared_by.username if device.clearances.first() else 'N/A'],
        ['Clearance Date', device.clearances.first().created_at.strftime("%Y-%m-%d") if device.clearances.first() else 'N/A'],
        ['Approved By', device.approved_by.username if device.approved_by else 'N/A'],
    ]
    remarks = device.reason_for_update or device.clearances.first().remarks or 'N/A'
    data.append(['Remarks', Paragraph(remarks, remarks_style)])

    table = Table(data, colWidths=[100*mm, 100*mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 12))

    user_history = device.user_history.all().order_by('assigned_date')
    if user_history.exists():
        history_data = [['Assignee Name', 'Email', 'Assigned By', 'Assigned Date', 'Cleared Date']]
        for history in user_history:
            assignee_name = f"{history.assignee_first_name or ''} {history.assignee_last_name or ''}".strip() or 'N/A'
            history_data.append([
                assignee_name,
                history.assignee_email_address or 'N/A',
                history.assigned_by.username if history.assigned_by else 'N/A',
                history.assigned_date.strftime("%Y-%m-%d") if history.assigned_date else 'N/A',
                history.cleared_date.strftime("%Y-%m-%d") if history.cleared_date else 'N/A',
            ])
        history_table = Table(history_data, colWidths=[40*mm, 40*mm, 40*mm, 40*mm, 40*mm])
        history_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        elements.append(Paragraph('User History', normal_style))
        elements.append(Spacer(1, 6))
        elements.append(history_table)
        elements.append(Spacer(1, 12))

    elements.append(Paragraph('Signature Section', footer_style))
    elements.append(Spacer(1, 6))
    signature_data = [
        ['Cleared By Signature:', ''],
        ['Date:', ''],
        ['Approved By Name & Signature:', ''],
        ['Date:', ''],
    ]
    signature_table = Table(signature_data, colWidths=[80*mm, 120*mm])
    signature_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(signature_table)

    import random
    def add_watermark(canvas, doc):
        watermark_text = "MOHI IT"
        canvas.saveState()
        canvas.setFont("Helvetica", 20)
        canvas.setFillGray(0.95, 0.95)
        page_width, page_height = doc.pagesize
        grid_size = 80
        placed_positions = []

        for x in range(0, int(page_width), grid_size):
            for y in range(0, int(page_height), grid_size):
                offset_x = random.randint(-40, 40)
                offset_y = random.randint(-40, 40)
                adjusted_x = x + offset_x
                adjusted_y = y + offset_y
                if (10 <= adjusted_x <= page_width - 10 and 
                    10 <= adjusted_y <= page_height - 10 and 
                    not any(abs(adjusted_x - px) < 50 or abs(adjusted_y - py) < 50 for px, py in placed_positions)):
                    canvas.rotate(45)
                    canvas.drawString(adjusted_x, adjusted_y, watermark_text)
                    canvas.rotate(-45)
                    placed_positions.append((adjusted_x, adjusted_y))

        canvas.restoreState()

    doc.build(elements, onFirstPage=add_watermark, onLaterPages=add_watermark)
    buffer.seek(0)
    return buffer