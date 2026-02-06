
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import Q, F, Case, When, IntegerField, Count
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta, datetime
from io import TextIOWrapper

# Models
from devices.models import CustomUser, DeviceAgreement, DeviceUserHistory, Employee, Import, Centre, Notification, PendingUpdate, Department
from devices.utils.devices_utils import generate_pdf_buffer
from devices.utils.emails import send_custom_email, send_custom_email, send_device_assignment_email
from it_operations.models import BackupRegistry, WorkPlan, IncidentReport, MissionCriticalAsset, WorkPlanTask
from devices.forms import ClearanceForm
from ppm.models import PPMTask, PPMPeriod, PPMActivity

# Third-party & Standard Library
import csv
import logging
from io import BytesIO

# Excel (openpyxl)
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

# PDF (ReportLab)
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    Frame, PageTemplate
)

# Django Shortcuts and HTTP
from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404

# Logging
logger = logging.getLogger(__name__)
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            logger.info(f"Successful login for user: {username}")
            return redirect('dashboard')
        else:
            logger.warning(f"Failed login attempt for username: {username}")
            messages.error(request, 'Invalid username or password.')
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('login')

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

@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_add(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        centre_id = request.POST.get('centre')
        is_trainer = request.POST.get('is_trainer') == 'on'
        is_staff = request.POST.get('is_staff') == 'on'
        is_superuser = request.POST.get('is_superuser') == 'on'
        groups = request.POST.getlist('groups')
        errors = []

        if not username:
            errors.append("Username is required.")
        if CustomUser.objects.filter(username=username).exists():
            errors.append("Username is already taken.")
        if not email:
            errors.append("Email is required.")
        if CustomUser.objects.filter(email=email).exists():
            errors.append("Email is already in use.")
        if not password:
            errors.append("Password is required.")
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
                user = CustomUser.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    centre=centre,
                    is_trainer=is_trainer,
                    is_staff=is_staff,
                    is_superuser=is_superuser
                )
                if groups:
                    user.groups.set(groups)
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
        password = request.POST.get('password')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        centre_id = request.POST.get('centre')
        is_trainer = request.POST.get('is_trainer') == 'on'
        is_staff = request.POST.get('is_staff') == 'on'
        is_superuser = request.POST.get('is_superuser') == 'on'
        groups = request.POST.getlist('groups')
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
                if password:
                    user.set_password(password)
                user.first_name = first_name
                user.last_name = last_name
                user.centre = centre
                user.is_trainer = is_trainer
                user.is_staff = is_staff
                user.is_superuser = is_superuser
                user.save()
                user.groups.clear()
                if groups:
                    user.groups.set(groups)
                messages.success(request, "User updated successfully.")
            return redirect('manage_users')
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

