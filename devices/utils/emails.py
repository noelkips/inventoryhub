from django.core.mail import EmailMultiAlternatives, EmailMessage
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string

# Detect test/environment mode
# - If DEBUG=True (local dev) → treat as test
# - If DB_NAME_CONFIG == 'ufdxwals_it_test_db' (staging/test site) → treat as test
# - Otherwise → production (live site)
IS_TEST_ENVIRONMENT = settings.DEBUG or (
    hasattr(settings, 'DB_NAME_CONFIG') and settings.DB_NAME_CONFIG == 'ufdxwals_it_test_db'
)

TEST_EMAIL_RECIPIENT = 'noel.langat@mohiafrica.org'


def send_custom_email(subject, message, recipient_list, attachment=None):
    """
    Legacy plain-text email sender with test-mode redirection.
    In test mode, all emails are redirected to TEST_EMAIL_RECIPIENT.
    """
    try:
        # In test mode: redirect everything to IT and add [TEST] prefix + note
        if IS_TEST_ENVIRONMENT:
            subject = f"[TEST EMAIL] {subject}"
            message = (
                f"--- THIS IS A TEST EMAIL (original recipients: {', '.join(recipient_list)}) ---\n\n"
                + message
            )
            final_recipient_list = [TEST_EMAIL_RECIPIENT]
            print(f"[TEST MODE] Email redirected to {TEST_EMAIL_RECIPIENT} (original: {recipient_list})")
        else:
            final_recipient_list = recipient_list

        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=final_recipient_list,
        )
        if attachment:
            filename, content, mimetype = attachment
            email.attach(filename, content, mimetype)

        email.send(fail_silently=False)
        print(f"Email sent successfully to {final_recipient_list}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def send_device_assignment_email(device, action='assigned', cleared_by=None):
    """
    Sends device assignment/clearance notification with test-mode redirection.
    In test mode, email goes only to IT with clear [TEST] marking and original recipient noted.
    """
    if not device.assignee:
        return  # No assignee → no email needed

    original_recipient = device.assignee.email
    if not original_recipient:
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

    # Plain text & HTML bodies
    plain_message = render_to_string('emails/device_notification.txt', context)
    html_message = render_to_string('emails/device_notification.html', context)

    subject_prefix = "Device Issued to You" if action == 'assigned' else "Device Cleared / Returned"
    subject = f"{subject_prefix}: {context['device_name']} ({device.serial_number})"

    try:
        # Test mode handling
        if IS_TEST_ENVIRONMENT:
            subject = f"[TEST EMAIL] {subject}"
            test_note = (
                f"\n\n--- THIS IS A TEST EMAIL ---\n"
                f"Original recipient: {original_recipient}\n"
                f"Original CC: {cc_email}\n"
                f"Environment: {'DEBUG' if settings.DEBUG else 'Test DB'}\n"
                f"--- END TEST NOTE ---\n\n"
            )
            plain_message = test_note + plain_message
            html_message = f"<p><strong>--- THIS IS A TEST EMAIL (original: {original_recipient}) ---</strong></p>" + html_message

            to_list = [TEST_EMAIL_RECIPIENT]
            cc_list = []  # No CC in test mode to avoid disturbing others
            print(f"[TEST MODE] Device {action} email redirected to {TEST_EMAIL_RECIPIENT} (original: {original_recipient})")
        else:
            to_list = [original_recipient]
            cc_list = [cc_email]

        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to_list,
            cc=cc_list,
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)
        print(f"Device {action} email sent to {to_list} (cc: {cc_list})")
        return True
    except Exception as e:
        print(f"Failed to send {action} email: {e}")
        return False