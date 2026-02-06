import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponse
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import inch
import base64
from ..models import CustomUser, Import, DeviceAgreement
from ..utils import send_custom_email


@login_required
def sign_issuance(request, pk):
    """Handle issuance signing - both IT staff and employee sign"""
    device = get_object_or_404(Import, pk=pk)

    if not device.assignee:
        messages.error(request, "Device must have an assignee before signing UAF.")
        return redirect('device_detail', pk=device.pk)

    # Auto-create agreement if missing
    agreement, created = DeviceAgreement.objects.get_or_create(
        device=device,
        employee=device.assignee,
        defaults={
            'issuance_it_user': request.user,
        }
    )

    if agreement.user_signed_issuance:
        messages.info(request, "This issuance agreement has already been signed.")
        return redirect('device_detail', pk=device.pk)

    category_display = device.get_category_display() or device.category or "device"

    if request.method == 'POST':
        user_sig = request.POST.get('user_signature_png', '').strip()
        it_sig = request.POST.get('it_signature_png', '').strip()
        agree = request.POST.get('agree_terms') == 'on'

        # Validation
        if not user_sig:
            messages.error(request, "Please draw your signature (employee).")
            return redirect('sign_issuance', pk=pk)

        if not it_sig:
            messages.error(request, "Please draw the IT staff signature.")
            return redirect('sign_issuance', pk=pk)

        if not agree:
            messages.error(request, "You must agree to the terms.")
            return redirect('sign_issuance', pk=pk)

        # Save both signatures
        agreement.issuance_user_signature_png = user_sig
        agreement.issuance_it_signature_png = it_sig
        agreement.issuance_date = timezone.now()
        agreement.issuance_it_user = request.user
        agreement.user_signed_issuance = True
        agreement.it_approved_issuance = True
        agreement.save()

        device.uaf_signed = True
        device.save()

        # Generate PDF
        pdf_buffer = BytesIO()
        generate_uaf_pdf(device, agreement, pdf_buffer, category_display)
        pdf_buffer.seek(0)

        # Email
        recipients = []
        if agreement.employee and agreement.employee.email:
            recipients.append(agreement.employee.email)
        recipients.append("it@mohiafrica.org")

        send_custom_email(
            subject=f"MOHI Device Issuance Agreement - {device.serial_number}",
            message="Your signed device issuance agreement is attached.",
            recipient_list=recipients,
            attachment=('MOHI_Device_Agreement.pdf', pdf_buffer.read(), 'application/pdf')
        )

        messages.success(request, "Issuance agreement signed successfully. PDF sent to your email.")
        return redirect('device_detail', pk=device.pk)

    context = {
        'device': device,
        'agreement': agreement,
        'category_display': category_display,
        'signing_type': 'issuance',
    }
    return render(request, 'import/sign_uaf.html', context)


@login_required
def sign_clearance(request, pk):
    """Handle clearance signing - ONLY employee signs when returning device"""
    device = get_object_or_404(Import, pk=pk)

    if not device.assignee:
        messages.error(request, "No assignee found for this device.")
        return redirect('device_detail', pk=device.pk)

    try:
        agreement = DeviceAgreement.objects.get(device=device, employee=device.assignee, is_archived=False)
    except DeviceAgreement.DoesNotExist:
        messages.error(request, "No active issuance agreement found. Device must be issued first.")
        return redirect('device_detail', pk=device.pk)

    if not agreement.user_signed_issuance:
        messages.error(request, "Issuance agreement must be signed before clearance.")
        return redirect('device_detail', pk=device.pk)

    if agreement.user_signed_clearance:
        messages.info(request, "This clearance has already been signed.")
        return redirect('device_detail', pk=device.pk)

    category_display = device.get_category_display() or device.category or "device"

    if request.method == 'POST':
        user_sig = request.POST.get('user_signature_png', '').strip()
        remarks = request.POST.get('remarks', '').strip()

        # Validation - only employee signature needed
        if not user_sig:
            messages.error(request, "Please draw your signature.")
            return redirect('sign_clearance', pk=pk)

        # Save employee signature and clearance info
        agreement.clearance_user_signature_png = user_sig
        agreement.clearance_date = timezone.now()
        agreement.clearance_it_user = request.user  # IT user processing the clearance
        agreement.user_signed_clearance = True
        agreement.it_approved_clearance = True
        agreement.clearance_remarks = remarks
        agreement.save()

        # Store employee info before clearing
        cleared_employee_name = device.assignee.full_name if device.assignee else 'Unknown'
        cleared_employee_email = device.assignee.email if device.assignee else None
        
        # Archive the agreement BEFORE clearing device
        agreement.is_archived = True
        agreement.save()
        
        # Clear device assignment
        device.assignee = None
        device.assignee_cache = ''
        device.status = 'Available'
        device.uaf_signed = False
        device.reason_for_update = f"Device cleared by {cleared_employee_name} on {timezone.now().date()}"
        device.save()

        # Generate PDF with both issuance and clearance
        pdf_buffer = BytesIO()
        generate_uaf_pdf(device, agreement, pdf_buffer, category_display, include_clearance=True)
        pdf_buffer.seek(0)

        # Email to employee and IT
        recipients = []
        if cleared_employee_email:
            recipients.append(cleared_employee_email)
        recipients.append("it@mohiafrica.org")

        send_custom_email(
            subject=f"MOHI Device Clearance Complete - {device.serial_number}",
            message=f"""
Dear {cleared_employee_name},

Your device clearance for {device.serial_number} ({category_display}) has been completed successfully.

Device Details:
- Serial Number: {device.serial_number}
- Device Type: {category_display}
- Cleared On: {timezone.now().date()}
- Cleared By IT Staff: {request.user.get_full_name() or request.user.username}

The complete UAF document (including issuance and clearance sections) is attached to this email for your records.

Best regards,
MOHI IT Department
            """,
            recipient_list=recipients,
            # recipient_list="noel.langat@mohiafrica.org",
            attachment=('MOHI_Device_Clearance_Complete.pdf', pdf_buffer.read(), 'application/pdf')
        )

        messages.success(request, f"Clearance signed successfully. Device {device.serial_number} has been cleared and is now available. Email sent to {cleared_employee_name}.")
        return redirect('device_detail', pk=device.pk)

    context = {
        'device': device,
        'agreement': agreement,
        'category_display': category_display,
        'signing_type': 'clearance',
    }
    return render(request, 'import/sign_uaf.html', context)


@login_required
def download_uaf_pdf(request, pk):
    """Download the UAF PDF"""
    device = get_object_or_404(Import, pk=pk)
    
    try:
        if device.assignee:
            agreement = DeviceAgreement.objects.get(device=device, employee=device.assignee)
        else:
            # Device cleared, get most recent agreement
            agreement = DeviceAgreement.objects.filter(device=device).order_by('-issuance_date').first()
            if not agreement:
                raise DeviceAgreement.DoesNotExist
    except DeviceAgreement.DoesNotExist:
        messages.error(request, "No agreement found for this device.")
        return redirect('device_detail', pk=device.pk)

    if not agreement.user_signed_issuance:
        messages.error(request, "This agreement has not been signed yet.")
        return redirect('device_detail', pk=device.pk)

    category_display = device.get_category_display() or device.category or "device"

    # Generate PDF
    pdf_buffer = BytesIO()
    include_clearance = agreement.user_signed_clearance
    generate_uaf_pdf(device, agreement, pdf_buffer, category_display, include_clearance)
    pdf_buffer.seek(0)

    # Determine filename
    if include_clearance:
        filename = f"MOHI_UAF_{device.serial_number}_Complete.pdf"
    else:
        filename = f"MOHI_UAF_{device.serial_number}.pdf"

    response = HttpResponse(pdf_buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
def download_past_uaf_pdf(request, agreement_id):
    """Download a specific past UAF agreement PDF by agreement ID"""
    agreement = get_object_or_404(DeviceAgreement, pk=agreement_id)
    device = agreement.device
    
    # Permission check
    if request.user.is_trainer and device.centre != request.user.centre:
        messages.error(request, "You don't have permission to access this document.")
        return redirect('display_approved_imports')
    
    if not agreement.user_signed_issuance:
        messages.error(request, "This agreement was never completed.")
        return redirect('device_history', pk=device.pk)
    
    category_display = device.get_category_display() or device.category or "device"
    
    # Determine if clearance should be included
    include_clearance = agreement.user_signed_clearance
    
    # Generate PDF
    pdf_buffer = BytesIO()
    generate_uaf_pdf(device, agreement, pdf_buffer, category_display, include_clearance=include_clearance)
    pdf_buffer.seek(0)
    
    # Prepare response
    filename = f"UAF_{device.serial_number}_{agreement.employee.full_name.replace(' ', '_')}_{agreement.issuance_date.strftime('%Y%m%d')}"
    if include_clearance:
        filename += f"_cleared_{agreement.clearance_date.strftime('%Y%m%d')}"
    filename += ".pdf"
    
    response = HttpResponse(pdf_buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

def generate_uaf_pdf(device, agreement, buffer, category_display, include_clearance=False):
    """Generate UAF PDF matching the original MOHI form exactly with clear sections"""
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Logo at very top with minimal padding - transparent background
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'document_title_1.png')
    if os.path.exists(logo_path):
        try:
            # Logo at top, no padding, with mask for transparency
            c.drawImage(logo_path, 50, height - 100, width=500, height=70, 
                       preserveAspectRatio=True, mask='auto')
        except:
            pass

    # Title - closer to logo
    y = height - 102
    c.setFont("Helvetica-Bold", 14)
    y -= 18
    c.drawCentredString(width/2, y, "MOHI DEVICE USAGE AGREEMENT FORM")

    # General information
    y -= 30
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "General information")
    
    y -= 15
    c.setFont("Helvetica", 9)
    
    # Compact general info
    general_info = [
        "• Only MOHI staff with a current MOHI ID may be assigned a work designated device (Laptop, iPad, Cellphone etc.).",
        "• The person who checked out the device is fully responsible for the device care.",
        "• All electronic devices must be used only at MOHI Centers and for the purpose of MOHI work.",
        "• All web browsing shall be dedicated to the achievement of MOHI work, no browsing of social media (Facebook, X,",
        "  Threads, Instagram, TikTok etc.), Music and Video streaming sites (Spotify, YouTube, etc.), torrent sites, or any sites",
        "  not conducive to the completion of MOHI work.",
    ]
    
    for line in general_info:
        c.drawString(50, y, line)
        y -= 11

    y -= 3
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, y, "Violation or misuse of any of these things will result in the confiscation of the device by the organization")
    y -= 11
    c.drawString(50, y, "and possible termination of the employee.")
    
    y -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "DO NOT LEAVE THE DEVICE UNATTENDED")
    
    y -= 15
    c.setFont("Helvetica", 9)
    c.drawString(50, y, "This agreement is binding for all staff and will be kept on file in the I.T Office.")

    # Agreement statements
    y -= 20
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, y, "By my signature below, I agree to all the following statements:")
    
    y -= 15
    c.setFont("Helvetica", 9)

    c.drawString(50, y, "• I have read, understood and accept the above conditions.")
    y -= 11
    c.drawString(50, y, "• I will not leave the device unattended.")
    y -= 15

    c.drawString(50, y, f"• I accept full responsibility for the {category_display} and accessories and agree to reimburse MOHI")
    y -= 11
    c.drawString(65, y, "for the full cost of repairing or replacing the device and accessories if they are lost, stolen, or damaged")
    y -= 11
    c.drawString(65, y, "while they are checked out in my name. I understand that leaving my center with a device constitutes theft.")
    y -= 11
    c.drawString(65, y, "If the exact model is no longer available, replacement cost will be the actual price of a similar laptop or")
    y -= 11
    c.drawString(65, y, "accessory in terms of quality, durability, and performance.")
    y -= 15

    c.drawString(50, y, "• I will not add, delete, or alter computer hardware, software, or settings without the go ahead from I.T")
    y -= 11
    c.drawString(65, y, "Department")
    y -= 15

    c.drawString(50, y, f"• I understand that this agreement is binding until the {category_display} is returned in good condition to")
    y -= 11
    c.drawString(65, y, "MOHI IT Department in case of departure, transfer or termination of employment.")
    y -= 25

    # ========== ISSUANCE TO STAFF SECTION (ALL IN ONE BORDER) ==========
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Issuance to Staff:")
    
    y -= 20
    
    # Get all information
    staff_name = agreement.employee.full_name if agreement.employee else 'N/A'
    mohi_id = agreement.employee.staff_number if agreement.employee and agreement.employee.staff_number else 'N/A'
    designation = agreement.employee.designation if agreement.employee and agreement.employee.designation else 'N/A'
    date_str = agreement.issuance_date.strftime('%d/%m/%Y') if agreement.issuance_date else 'Pending'
    
    it_staff_first_name = agreement.issuance_it_user.first_name if agreement.issuance_it_user and agreement.issuance_it_user.first_name else 'N/A'
    it_staff_last_name = agreement.issuance_it_user.last_name if agreement.issuance_it_user and agreement.issuance_it_user.last_name else 'N/A'
    it_staff_full_name = f"{it_staff_first_name} {it_staff_last_name}"
    
    # Single large border for entire issuance section
    box_height = 135
    box_width = width - 100
    
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.setLineWidth(1.5)
    c.rect(50, y - box_height, box_width, box_height)
    
    # Define 3 columns
    col1_x = 60  # Staff Details
    col2_x = 215  # Signature & Date
    col3_x = 390  # Device Information
    
    # ===== ROW 1: STAFF MEMBER =====
    row1_y = y - 15
    
    # Column 1 - Staff Details
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col1_x, row1_y, "STAFF DETAILS")
    row1_y -= 13
    
    c.setFont("Helvetica-Bold", 8)
    c.drawString(col1_x, row1_y, f"Name: {staff_name}")
    row1_y -= 10
    c.drawString(col1_x, row1_y, f"Staff Number: {mohi_id}")
    row1_y -= 10
    c.drawString(col1_x, row1_y, f"Designation: {designation}")
    
    # Column 2 - Staff Signature & Date
    row1_y = y - 15
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col2_x, row1_y, "STAFF SIGNATURE")
    row1_y -= 13
    
    c.setFont("Helvetica", 7)
    c.drawString(col2_x, row1_y, "Employee/Staff Member:")
    c.drawString(col2_x, row1_y, "Employee/Staff Member:")
    # Add small vertical padding so signature won't overlap surrounding text
    row1_y -= 4

    # Draw a small white background rectangle behind the signature area to ensure clear separation
    sig_rect_x = col2_x - 3
    sig_rect_y = row1_y - 32 - 3
    sig_rect_w = 100 + 6
    sig_rect_h = 45 + 6
    c.setFillColorRGB(1, 1, 1)
    c.rect(sig_rect_x, sig_rect_y, sig_rect_w, sig_rect_h, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    
    # Employee signature
    if agreement.issuance_user_signature_png:
        try:
            sig_data = agreement.issuance_user_signature_png.split(',')[1] if ',' in agreement.issuance_user_signature_png else agreement.issuance_user_signature_png
            sig_bytes = base64.b64decode(sig_data)
            sig_image = ImageReader(BytesIO(sig_bytes))
            c.drawImage(sig_image, col2_x, row1_y - 32, width=100, height=45, 
                       preserveAspectRatio=True, mask='auto')
        except:
            pass
    
   
    
    
    # Column 3 - Device Information
    row1_y = y - 15
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col3_x, row1_y, "DEVICE INFORMATION")
    row1_y -= 13
    
    c.setFont("Helvetica", 8)
    c.drawString(col3_x, row1_y, f"Device Type: {category_display}")
    row1_y -= 10
    c.drawString(col3_x, row1_y, f"Serial No: {device.serial_number}")
    row1_y -= 10
    c.drawString(col3_x, row1_y, f"Date Issued: {date_str}")
    
    # ===== ROW 2: IT STAFF (Issuing) =====
    row2_y = y - 75
    
    # Column 1 - IT Staff Details
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col1_x, row2_y, "ISSUING IT STAFF DETAILS")
    row2_y -= 13
    
    c.setFont("Helvetica", 8)
    c.drawString(col1_x, row2_y, f"Name: {it_staff_full_name}")
    row2_y -= 10
    c.drawString(col1_x, row2_y, f"Department: I.T Department")
    
    # Column 2 - IT Staff Signature & Date
    row2_y = y - 75
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col2_x, row2_y, "IT STAFF SIGNATURE")
    row2_y -= 13
    
    c.setFont("Helvetica", 7)
    c.drawString(col2_x, row2_y, "I.T Department Staff:")
    
    # IT Staff signature
    if agreement.issuance_it_signature_png:
        try:
            sig_data = agreement.issuance_it_signature_png.split(',')[1] if ',' in agreement.issuance_it_signature_png else agreement.issuance_it_signature_png
            sig_bytes = base64.b64decode(sig_data)
            sig_image = ImageReader(BytesIO(sig_bytes))
            c.drawImage(sig_image, col2_x, row2_y - 32, width=100, height=35, 
                       preserveAspectRatio=True, mask='auto')
        except:
            pass
    
    c.setFont("Helvetica", 7)
    c.drawString(col2_x, row2_y - 38, f"Date: {date_str}")
    
    y -= (box_height + 20)

    # ========== CLEARANCE SECTION ==========
    if include_clearance and agreement.user_signed_clearance:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "Handing Over to I.T Department")
        
        y -= 20
        
        clearance_date = agreement.clearance_date.strftime('%d/%m/%Y') if agreement.clearance_date else 'Pending'
        
        # Get clearance IT staff details
        clearance_it_first = agreement.clearance_it_user.first_name if agreement.clearance_it_user and agreement.clearance_it_user.first_name else 'N/A'
        clearance_it_last = agreement.clearance_it_user.last_name if agreement.clearance_it_user and agreement.clearance_it_user.last_name else 'N/A'
        clearance_it_full = f"{clearance_it_first} {clearance_it_last}"
        
        # ===== GROUPED: STAFF RETURNING & IT WITNESS =====
        clearance_box_height = 75
        box_width = width - 100
        
        c.setStrokeColorRGB(0, 0.4, 0)  # Dark green
        c.setLineWidth(1.5)
        c.rect(50, y - clearance_box_height, box_width, clearance_box_height)
        
        # Left column - Staff Member Signature
        col1_x = 60
        col2_x = width / 2 + 20
        
        sig_y = y - 15
        c.setFont("Helvetica-Bold", 9)
        c.drawString(col1_x, sig_y, "STAFF SIGNATURE (Returning Device)")
        sig_y -= 12
        
        c.setFont("Helvetica", 7)
        c.drawString(col1_x, sig_y, "Staff Member:")
        sig_y -= 15
        
        c.setFont("Helvetica", 7)
        c.drawString(col1_x, sig_y, "  ")
        
        # Employee clearance signature
        
        
        if agreement.clearance_user_signature_png:
            try:
                sig_data = agreement.clearance_user_signature_png.split(',')[1] if ',' in agreement.clearance_user_signature_png else agreement.clearance_user_signature_png
                sig_bytes = base64.b64decode(sig_data)
                sig_image = ImageReader(BytesIO(sig_bytes))
                c.drawImage(sig_image, col1_x, sig_y - 40, width=150, height=60, 
                           preserveAspectRatio=True, mask='auto')
            except:
                pass
        
        # c.setFont("Helvetica", 7)
        # c.drawString(col1_x, sig_y - 42, f"Date: {clearance_date}")
        
        # Right column - IT Staff Witness
        sig_y = y - 15
        c.setFont("Helvetica-Bold", 9)
        c.drawString(col2_x, sig_y, "I.T STAFF (Witness)")
        sig_y -= 12
        
        c.setFont("Helvetica", 8)
        c.drawString(col2_x, sig_y, f"Name: {clearance_it_full}")
        sig_y -= 10
        c.drawString(col2_x, sig_y, f"Department: I.T Department")
        sig_y -= 10
        c.drawString(col2_x, sig_y, f"Date: {clearance_date}")
        
        y -= (clearance_box_height + 15)

        # Remarks if any
        if hasattr(agreement, 'clearance_remarks') and agreement.clearance_remarks:
            c.setFont("Helvetica-Bold", 8)
            c.drawString(50, y, "Remarks:")
            y -= 12
            c.setFont("Helvetica", 8)
            # Wrap remarks text if too long
            remarks_text = agreement.clearance_remarks
            max_width = box_width - 20
            words = remarks_text.split()
            lines = []
            current_line = []
            
            for word in words:
                current_line.append(word)
                test_line = ' '.join(current_line)
                if c.stringWidth(test_line, "Helvetica", 8) > max_width:
                    current_line.pop()
                    lines.append(' '.join(current_line))
                    current_line = [word]
            
            if current_line:
                lines.append(' '.join(current_line))
            
            for line in lines[:3]:  # Max 3 lines for remarks
                c.drawString(50, y, line)
                y -= 10

    c.save()