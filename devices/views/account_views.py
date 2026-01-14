from django.shortcuts import render, redirect
from django.contrib import messages
from ..models import CustomUser 
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string
from django.db.models import Q
from ..utils import send_custom_email 
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_safe

@require_safe
def session_ping(request):
    # Just touch the session → extends it
    request.session.modified = True
    return JsonResponse({"status": "ok"})


def password_reset_request(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        if not email:
            messages.error(request, "Please enter an email address.")
            return render(request, 'accounts/password_reset_request.html')

        # Find all active users with this email.
        # Use CustomUser model
        associated_users = CustomUser.objects.filter(Q(email=email) & Q(is_active=True))

        if not associated_users.exists():
            messages.error(request, "No active user found with that email address.")
            return render(request, 'accounts/password_reset_request.html')
        
        # We'll send a reset link to all users with this email.
        for user in associated_users:
            # Generate token and user ID
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Build the reset link
            current_site = request.get_host()
            relative_link = f'/accounts/reset/{uid}/{token}/'
            reset_url = f'http://{current_site}{relative_link}' # Use https in production

            # Create email content
            subject = 'Password Reset Request for InventoryHub'
            
            # Use a template for the email body
            email_body = render_to_string('accounts/password_reset_email.txt', {
                'user': user,
                'reset_url': reset_url,
            })
            
            # Use our utility function to send the email
            send_custom_email(subject, email_body, [user.email])

        messages.success(request, "If an account exists, we've sent instructions to reset your password.")
        return redirect('password_reset_sent')

    return render(request, 'accounts/password_reset_request.html')


def password_reset_sent(request):
    """
    A simple confirmation page.
    """
    return render(request, 'accounts/password_reset_sent.html')


def password_reset_confirm(request, uidb64=None, token=None):
    try:
        # Decode the user ID
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    # Check if the user exists and the token is valid
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            new_password1 = request.POST.get('new_password1')
            new_password2 = request.POST.get('new_password2')
            errors = []

            if not new_password1 or not new_password2:
                errors.append("Both password fields are required.")
            if new_password1 != new_password2:
                errors.append("New passwords do not match.")
            if len(new_password1) < 8:
                errors.append("New password must be at least 8 characters long.")
            
            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                user.set_password(new_password1)
                user.save()
                messages.success(request, "Password has been reset successfully. You can now log in.")
                return redirect('login') # Redirect to the login page

        # GET request: show the password reset form
        return render(request, 'accounts/password_reset_new.html')
    else:
        # Invalid link
        messages.error(request, "The password reset link is invalid or has expired.")
        return render(request, 'accounts/password_reset_invalid.html')