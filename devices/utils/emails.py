from django.core.mail import EmailMessage
from django.conf import settings

def send_custom_email(subject, message, recipient_list, attachment=None):
    """
    A utility function to send an email.
    recipient_list: list of emails, e.g., ['user@example.com']
    attachment: tuple containing (filename, content, mimetype) -> Optional
    """
    try:
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipient_list,
        )

        # If an attachment is provided, add it
        if attachment:
            # attachment format expected: ('filename.pdf', pdf_bytes, 'application/pdf')
            filename, content, mimetype = attachment
            email.attach(filename, content, mimetype)

        email.send(fail_silently=False)
        print(f"Email sent successfully to {recipient_list}")
        return True
    except Exception as e:
        print(f"Error sending email to {recipient_list}: {e}")
        return False