from django.core.mail import EmailMultiAlternatives, EmailMessage
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string  # optional – for nicer HTML

def send_custom_email(subject, message, recipient_list, attachment=None):
    """
    Legacy plain-text email sender (kept for compatibility)
    """
    try:
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipient_list,
        )
        if attachment:
            filename, content, mimetype = attachment
            email.attach(filename, content, mimetype)
        email.send(fail_silently=False)
        print(f"Email sent successfully to {recipient_list}")
        return True
    except Exception as e:
        print(f"Error sending email to {recipient_list}: {e}")
        return False


def send_device_assignment_email(device, action='assigned', cleared_by=None):
    """
    Sends notification when a device is assigned or cleared.
    
    Args:
        device: Import instance
        action: 'assigned' or 'cleared'
        cleared_by: CustomUser instance (only needed when action='cleared')
    """
    if not device.assignee:
        return  # No assignee → no email needed for assignment

    recipient = device.assignee.email
    if not recipient:
        print(f"No email for assignee {device.assignee} — skipping notification")
        return

    cc_email = "it@mohiafrica.org"

    context = {
        'action': action,
        'device': device,
        'assignee': device.assignee,
        'issued_by': device.added_by if action == 'assigned' else cleared_by,
        'issued_at': timezone.now(),
        'centre': device.centre,
        'department': device.department,
        'serial': device.serial_number,
        'device_name': device.device_name or device.system_model or 'Unknown device',
        'category': dict(device.CATEGORY_CHOICES).get(device.category, device.category),
    }

    # Plain text version
    plain_message = render_to_string('emails/device_notification.txt', context)

    # HTML version (better readability)
    html_message = render_to_string('emails/device_notification.html', context)

    subject_prefix = "Device Issued to You" if action == 'assigned' else "Device Cleared / Returned"
    subject = f"{subject_prefix}: {context['device_name']} ({device.serial_number})"

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
            cc=[cc_email],
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)
        print(f"Device {action} email sent to {recipient} (cc: {cc_email})")
        return True
    except Exception as e:
        print(f"Failed to send {action} email to {recipient}: {e}")
        return False