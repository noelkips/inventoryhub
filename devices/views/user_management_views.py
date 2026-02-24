
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import Group, Permission
from django.conf import settings
from django.db import transaction
from devices.models import CustomUser, Centre
# Third-party & Standard Library
import csv
import logging
from io import BytesIO


# Django Shortcuts and HTTP
from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404

# Logging
logger = logging.getLogger(__name__)
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache


TEST_LOGIN_BYPASS_PASSWORD = "Mohiit@2026"
IS_TEST_ENVIRONMENT = settings.DEBUG or (
    hasattr(settings, 'DB_NAME_CONFIG') and settings.DB_NAME_CONFIG == 'ufdxwals_it_test_db'
)
from django.utils.crypto import get_random_string
from devices.utils.emails import send_custom_email




def is_safe_url(url, allowed_host):
    """
    Check if a URL is safe for redirection.
    Prevents open redirect vulnerabilities.
    """
    from urllib.parse import urlparse
    
    if not url:
        return False
    
    # Don't allow URLs that start with multiple slashes or backslashes
    if url.startswith('///') or url.startswith('\\\\'):
        return False
    
    # Parse the URL
    parsed = urlparse(url)
    
    # Check if it's a relative URL (no scheme and no netloc)
    if not parsed.scheme and not parsed.netloc:
        return True
    
    # If it has a scheme or netloc, ensure it matches the allowed host
    if parsed.netloc:
        return parsed.netloc == allowed_host
    
    return False


@never_cache
def login_view(request):
    # If already authenticated, handle redirect
    if request.user.is_authenticated:
        next_url = request.GET.get('next') or request.POST.get('next')
        if next_url and is_safe_url(next_url, request.get_host()):
            return redirect(next_url)
        return redirect('dashboard')
    
    if request.method == 'POST':
        login_identifier = request.POST.get('username', '').strip()
        password = request.POST.get('password')
        next_url = request.POST.get('next', '').strip()  # Get next parameter

        user = authenticate(request, username=login_identifier, password=password)

        # Allow login via email address as well
        if user is None and login_identifier:
            email_user = CustomUser.objects.filter(email__iexact=login_identifier).first()
            if email_user:
                user = authenticate(request, username=email_user.username, password=password)

        # Non-production login bypass password (localhost / test site only)
        if (
            user is None and
            IS_TEST_ENVIRONMENT and
            password == TEST_LOGIN_BYPASS_PASSWORD and
            login_identifier
        ):
            bypass_user = (
                CustomUser.objects.filter(username__iexact=login_identifier).first()
                or CustomUser.objects.filter(email__iexact=login_identifier).first()
            )
            if bypass_user and bypass_user.is_active:
                bypass_user.backend = settings.AUTHENTICATION_BACKENDS[0]
                user = bypass_user
                logger.warning(
                    "Test login bypass used for user '%s' on %s",
                    bypass_user.username,
                    request.get_host()
                )
        
        if user is not None:
            login(request, user)
            logger.info(f"Successful login for user: {login_identifier}")
            
            # Redirect to 'next' if it exists and is safe, otherwise dashboard
            if next_url and is_safe_url(next_url, request.get_host()):
                return redirect(next_url)
            return redirect('dashboard')
        else:
            logger.warning(f"Failed login attempt for username/email: {login_identifier}")
            messages.error(request, 'Invalid username or password.')
            # Preserve 'next' parameter on failed login
            if next_url:
                return render(request, 'login.html', {'next': next_url})
    
    # GET request - preserve 'next' parameter
    next_url = request.GET.get('next', '')
    context = {'next': next_url} if next_url else {}
    return render(request, 'login.html', context)


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('landing_page')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def manage_users(request):
    users = CustomUser.objects.all()
    centres = Centre.objects.all()
    groups = Group.objects.all()
    permissions = Permission.objects.all()
    for user in users:
        user.stats = {
            'devices_added': user.imports_added.count(),
            'devices_approved': user.imports_approved.count() if request.user.is_superuser else 0,
            'devices_updated': user.pending_updates.count() if request.user.is_trainer else 0
        }
    return render(request, 'manage_users.html', {
        'users': users,
        'centres': centres,
        'groups': groups,
        'permissions': permissions
    })


def _send_user_credentials_email(request, user, temp_password):
    assigned_group_names = list(user.groups.values_list('name', flat=True))
    role_labels = []
    if user.is_superuser:
        role_labels.append("Superuser")
    if user.is_staff:
        role_labels.append("Staff")
    if user.is_trainer:
        role_labels.append("Trainer")
    if getattr(user, 'is_it_manager', False):
        role_labels.append("IT Manager")
    if getattr(user, 'is_senior_it_officer', False):
        role_labels.append("Senior IT Officer")
    if not role_labels:
        role_labels.append("User")

    login_url = request.build_absolute_uri('/login/')
    return send_custom_email(
        subject="Your Mohiit.org Account Credentials",
        message=(
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"Your Mohiit.org account credentials are below.\n"
            f"Login URL: {login_url}\n"
            f"Username: {user.username}\n"
            f"Temporary Password: {temp_password}\n"
            f"Assigned Roles: {', '.join(role_labels)}\n"
            f"Assigned Groups: {', '.join(assigned_group_names) if assigned_group_names else 'None'}\n"
            f"Centre: {user.centre.name if user.centre else 'N/A'}\n\n"
            f"Please log in and change your password immediately."
        ),
        recipient_list=[user.email],
    )

@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_add(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        centre_id = request.POST.get('centre')
        is_trainer = request.POST.get('is_trainer') == 'on'
        is_staff = request.POST.get('is_staff') == 'on'
        is_superuser = request.POST.get('is_superuser') == 'on'
        is_active = request.POST.get('is_active') == 'on'
        groups = [group_id for group_id in request.POST.getlist('groups') if str(group_id).strip()]
        errors = []

        if not username:
            errors.append("Username is required.")
        if CustomUser.objects.filter(username=username).exists():
            errors.append("Username is already taken.")
        if not email:
            errors.append("Email is required.")
        if CustomUser.objects.filter(email=email).exists():
            errors.append("Email is already in use.")
        if centre_id and centre_id != '' and not Centre.objects.filter(id=centre_id).exists():
            errors.append("Invalid centre selected.")
        if is_trainer and not centre_id:
            errors.append("Centre is required for trainers.")
        if is_superuser:
            centre_id = None

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            with transaction.atomic():
                centre = Centre.objects.get(id=centre_id) if centre_id and centre_id != '' else None
                temp_password = get_random_string(12)
                user = CustomUser.objects.create_user(
                    username=username,
                    email=email,
                    password=temp_password,
                    first_name=first_name,
                    last_name=last_name,
                    centre=centre,
                    is_trainer=is_trainer,
                    is_staff=is_staff,
                    is_superuser=is_superuser,
                    is_active=is_active
                )
                if groups:
                    user.groups.set(groups)
                _send_user_credentials_email(request, user, temp_password)
                messages.success(request, "User added successfully.")
                return redirect('manage_users')
    return redirect('manage_users')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_update(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        centre_id = request.POST.get('centre')
        is_trainer = request.POST.get('is_trainer') == 'on'
        is_staff = request.POST.get('is_staff') == 'on'
        is_superuser = request.POST.get('is_superuser') == 'on'
        is_active = request.POST.get('is_active') == 'on'
        groups = [group_id for group_id in request.POST.getlist('groups') if str(group_id).strip()]
        errors = []

        if not username:
            errors.append("Username is required.")
        if CustomUser.objects.filter(username=username).exclude(id=pk).exists():
            errors.append("Username is already taken.")
        if not email:
            errors.append("Email is required.")
        if CustomUser.objects.filter(email=email).exclude(id=pk).exists():
            errors.append("Email is already in use.")
        if centre_id and centre_id != '' and not Centre.objects.filter(id=centre_id).exists():
            errors.append("Invalid centre selected.")
        if is_trainer and not centre_id:
            errors.append("Centre is required for trainers.")
        if is_superuser:
            centre_id = None

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            with transaction.atomic():
                centre = Centre.objects.get(id=centre_id) if centre_id and centre_id != '' else None
                user.username = username
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                user.centre = centre
                user.is_trainer = is_trainer
                user.is_staff = is_staff
                user.is_superuser = is_superuser
                user.is_active = is_active
                user.save()
                user.groups.clear()
                if groups:
                    user.groups.set(groups)
                messages.success(request, "User updated successfully.")
            return redirect('manage_users')
    return redirect('manage_users')


@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def resend_user_credentials(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)

    if not user.email:
        messages.error(request, f"User '{user.username}' has no email address.")
        return redirect('manage_users')

    temp_password = get_random_string(12)
    user.set_password(temp_password)
    user.save(update_fields=['password'])

    if _send_user_credentials_email(request, user, temp_password):
        messages.success(request, f"Credentials sent to {user.email}.")
    else:
        messages.error(request, f"Failed to send credentials to {user.email}.")

    return redirect('manage_users')

    
def _can_delete_user(user):
    """Only IT Manager or Senior IT Officer can delete users."""
    return user.is_it_manager or user.is_senior_it_officer

@login_required
@user_passes_test(_can_delete_user, login_url='manage_users')
def user_delete(request, pk):
    user_to_delete = get_object_or_404(CustomUser, pk=pk)

    if request.method == 'POST':
        if user_to_delete == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect('manage_users')

        with transaction.atomic():
            username = user_to_delete.username
            user_to_delete.delete()
            messages.success(request, f"User '{username}' deleted successfully.")
        return redirect('manage_users')

    return redirect('manage_users')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def manage_groups(request):
    if request.method == 'POST':
        group_name = request.POST.get('group_name')
        if group_name:
            if not Group.objects.filter(name=group_name).exists():
                Group.objects.create(name=group_name)
                messages.success(request, f"Group '{group_name}' created successfully.")
            else:
                messages.error(request, "Group name already exists.")
        return redirect('manage_users')
    return render(request, 'manage_users.html', {'groups': Group.objects.all()})

@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_group(request):
    if request.method == 'POST':
        group_id = request.POST.get('group_id')
        group = get_object_or_404(Group, id=group_id)
        group.delete()
        messages.success(request, "Group deleted successfully.")
    return redirect('manage_users')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def update_group_permissions(request):
    if request.method == 'POST':
        group_id = request.POST.get('group_id')
        permission_ids = request.POST.getlist('permissions')
        group = get_object_or_404(Group, id=group_id)
        group.permissions.clear()
        if permission_ids:
            group.permissions.set(permission_ids)
        messages.success(request, "Permissions updated successfully.")
        return redirect('manage_users')
    return redirect('manage_users')

