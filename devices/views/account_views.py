from django.shortcuts import render, redirect
from django.contrib import messages
from ..models import CustomUser 
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.utils.http import url_has_allowed_host_and_scheme
from django.template.loader import render_to_string
from django.db.models import Q
from ..utils import send_custom_email 
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_safe
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import Q, F, Case, When, IntegerField, Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect, StreamingHttpResponse
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta, datetime
from io import TextIOWrapper

# Models
from devices.models import CustomUser, DeviceAgreement, DeviceRepair, DeviceUserHistory, Employee, Import, Centre, Notification, PendingUpdate, Department
from devices.utils.devices_utils import generate_pdf_buffer
from devices.utils.emails import send_custom_email, send_custom_email, send_device_assignment_email
from devices.utils.signatures import normalize_signature_data_url
from it_operations.models import BackupRegistry, WorkPlan, IncidentReport, MissionCriticalAsset, WorkPlanTask
from devices.forms import ClearanceForm
from devices.utils.notification_utils import (
    build_notification_preview,
    is_workflow_request_notification,
    resolve_related_import,
    sync_notification_state,
    sync_stale_workflow_notifications,
)
from ppm.models import PPMTask, PPMPeriod, PPMActivity
from devices.utils.inventory_centre_report import build_inventory_workbook, get_inventory_devices

# Third-party & Standard Library
import csv
import logging
import json
import time
from urllib.parse import urlparse
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


def _notification_target_url(notification):
    related_import = resolve_related_import(notification)
    if related_import:
        return reverse('device_detail', args=[related_import.pk])

    if notification.content_type and notification.related_object:
        if notification.content_type.model == 'devicerepair' and getattr(notification.related_object, 'device_id', None):
            return reverse('device_repairs', args=[notification.related_object.device_id])
    return reverse('notifications_view')


def _notification_target_label(notification):
    if notification.content_type and notification.content_type.model == 'devicerepair':
        return 'Open Repair'
    if notification.content_type and notification.content_type.model in {'import', 'pendingupdate'}:
        return 'Open Device'
    return 'Open Related Item'


def _notification_action_urls(notification, user):
    approve_url = None
    clarify_url = None
    related_import = resolve_related_import(notification)

    if (
        user.is_superuser
        and not user.is_trainer
        and notification.content_type
        and related_import
        and not related_import.is_approved
        and notification.content_type.model in {'pendingupdate', 'import'}
    ):
        approve_url = reverse('import_approve', args=[related_import.pk])
        clarify_url = reverse('import_reject', args=[related_import.pk])

    return approve_url, clarify_url


def _prepare_notification(notification, user):
    notification = sync_notification_state(notification)
    related_import = resolve_related_import(notification)
    notification.detail_url = reverse('notification_detail', args=[notification.pk])
    notification.target_url = _notification_target_url(notification)
    notification.target_label = _notification_target_label(notification)
    notification.has_related_target = notification.target_url != reverse('notifications_view')
    notification.approve_url, notification.clarify_url = _notification_action_urls(notification, user)
    notification.can_review_request = bool(notification.approve_url and notification.clarify_url)
    notification.preview_message = build_notification_preview(notification.message, length=220)
    notification.dropdown_preview_message = build_notification_preview(notification.message, length=120)
    notification.is_workflow_request = is_workflow_request_notification(notification)
    notification.related_import_is_approved = bool(related_import and related_import.is_approved)
    return notification


def _safe_next_url(request, *, default_url, deleted_notification_pk=None):
    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER')
    if not next_url:
        return default_url

    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return default_url

    if deleted_notification_pk is not None:
        deleted_path = reverse('notification_detail', args=[deleted_notification_pk])
        if urlparse(next_url).path == deleted_path:
            return default_url

    return next_url


def _can_download_inventory_centre_report(user):
    return bool(user.is_authenticated and (user.is_superuser or user.is_it_manager))


def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html', {})

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
    

@login_required
def notifications_view(request):
    sync_stale_workflow_notifications(request.user)
    qs = Notification.objects.filter(user=request.user).select_related('content_type', 'responded_by').order_by('is_read', '-created_at')
    unread_count = qs.filter(is_read=False).count()

    unread_only = str(request.GET.get('unread', '')).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    if unread_only:
        qs = qs.filter(is_read=False)

    notifications = [_prepare_notification(notification, request.user) for notification in qs]

    return render(request, 'notifications.html', {'notifications': notifications, 'unread_count': unread_count})


@login_required
@require_safe
def notification_detail(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification = sync_notification_state(notification)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=['is_read'])

    notification = _prepare_notification(notification, request.user)
    back_url = reverse('notifications_view')

    return render(request, 'notification_detail.html', {
        'notification': notification,
        'back_url': back_url,
    })


@login_required
def clear_all_notifications(request):
    if request.method == 'POST':
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        wants_json = 'application/json' in (request.headers.get('Accept') or '') or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if wants_json:
            return JsonResponse({'ok': True})

        messages.success(request, "All notifications cleared.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/dashboard/'))
    return HttpResponseRedirect('/dashboard/')



@login_required
def profile(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        staff_signature_png = (request.POST.get('staff_signature_png') or '').strip()
        clear_signature = (request.POST.get('clear_signature') == 'on')
        user = request.user
        errors = []

        if not username:
            errors.append("Username is required.")
        if CustomUser.objects.exclude(id=user.id).filter(username=username).exists():
            errors.append("Username is already taken.")
        if not email:
            errors.append("Email is required.")
        if CustomUser.objects.exclude(id=user.id).filter(email=email).exists():
            errors.append("Email is already in use.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            if clear_signature:
                user.staff_signature_png = ''
            elif staff_signature_png:
                user.staff_signature_png = normalize_signature_data_url(staff_signature_png)
            user.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('profile')

    staff_signature_preview = (getattr(request.user, "staff_signature_png", "") or "").strip()
    if staff_signature_preview and not staff_signature_preview.startswith("data:"):
        # Backwards compatibility if only raw base64 was stored.
        staff_signature_preview = f"data:image/png;base64,{staff_signature_preview}"

    return render(request, 'accounts/profile.html', {
        'user': request.user,
        'centres': Centre.objects.all(),
        'staff_signature_preview': staff_signature_preview,
    })



@login_required
def change_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        errors = []

        if not old_password or not new_password1 or not new_password2:
            errors.append("All password fields are required.")
        if new_password1 != new_password2:
            errors.append("New passwords do not match.")
        if len(new_password1) < 8:
            errors.append("New password must be at least 8 characters long.")
        if not request.user.check_password(old_password):
            errors.append("Current password is incorrect.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            request.user.set_password(new_password1)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, "Password changed successfully.")
            return redirect('change_password')
    return render(request, 'accounts/change_password.html', {})



from ..utils import unknown_device_name_q

device_name_CATEGORIES = {
    'laptop': Q(device_name__icontains='laptop'),
    'monitor': Q(device_name__icontains='monitor'),
    'system unit': Q(device_name__icontains='system unit'),
    'printer': Q(device_name__icontains='printer'),
    'routers/switch/server': Q(device_name__icontains='router') | Q(device_name__icontains='switch') | Q(device_name__icontains='server'),
    'n-computing': Q(device_name__icontains='N-Computing'),
    'television': Q(device_name__icontains='television'),
}



@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if request.method != 'POST':
        return HttpResponseRedirect('/dashboard/')

    notification.is_read = True
    notification.save(update_fields=['is_read'])

    wants_json = 'application/json' in (request.headers.get('Accept') or '') or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if wants_json:
        return JsonResponse({'ok': True})

    messages.success(request, "Notification marked as read.")
    return HttpResponseRedirect(
        _safe_next_url(request, default_url=reverse('notifications_view'))
    )


@login_required
@require_POST
def delete_notification(request, pk):
    Notification.objects.filter(pk=pk, user=request.user).delete()

    wants_json = 'application/json' in (request.headers.get('Accept') or '') or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if wants_json:
        return JsonResponse({'ok': True})

    messages.success(request, "Notification removed.")
    return HttpResponseRedirect(
        _safe_next_url(
            request,
            default_url=reverse('notifications_view'),
            deleted_notification_pk=pk,
        )
    )


@login_required
@require_safe
def notifications_api(request):
    sync_stale_workflow_notifications(request.user)
    try:
        limit = int(request.GET.get('limit', 8))
    except ValueError:
        limit = 8
    limit = max(1, min(limit, 25))

    qs = Notification.objects.filter(user=request.user).select_related('content_type', 'responded_by').order_by('is_read', '-created_at')
    unread_count = qs.filter(is_read=False).count()
    items = []
    for n in qs[:limit]:
        n = _prepare_notification(n, request.user)
        items.append({
            'id': n.pk,
            'message': n.message,
            'created_at': n.created_at.isoformat(),
            'created_at_display': n.created_at.strftime('%b %d, %Y %H:%M'),
            'is_read': n.is_read,
            'url': n.detail_url,
            'target_url': n.target_url,
            'target_label': n.target_label,
        })

    return JsonResponse({'unread_count': unread_count, 'items': items})


@login_required
@require_safe
def notifications_stream(request):
    user_id = request.user.id
    try:
        poll_seconds = float(request.GET.get('poll', 3))
    except ValueError:
        poll_seconds = 3
    poll_seconds = max(1.0, min(poll_seconds, 10.0))

    def event_stream():
        last_state = None
        # Keep the connection alive; client will reconnect if needed
        while True:
            sync_stale_workflow_notifications(request.user)
            qs = Notification.objects.filter(user_id=user_id).select_related('content_type', 'responded_by').order_by('is_read', '-created_at')
            unread_count = qs.filter(is_read=False).count()
            latest_id = qs.values_list('id', flat=True).first() or 0
            state = (unread_count, latest_id)

            if state != last_state:
                items = []
                for n in qs[:8]:
                    prepared = _prepare_notification(n, request.user)
                    items.append({
                        'id': prepared.pk,
                        'message': prepared.message,
                        'created_at': prepared.created_at.isoformat(),
                        'created_at_display': prepared.created_at.strftime('%b %d, %Y %H:%M'),
                        'is_read': prepared.is_read,
                        'url': prepared.detail_url,
                        'target_url': prepared.target_url,
                        'target_label': prepared.target_label,
                    })
                payload = {
                    'unread_count': unread_count,
                    'items': items,
                }
                yield f"event: notifications\ndata: {json.dumps(payload)}\n\n"
                last_state = state
            else:
                yield "event: ping\ndata: {}\n\n"

            time.sleep(poll_seconds)

    resp = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp



@login_required
def dashboard_view(request):
    user = request.user
    can_switch_dashboard_scope = bool((user.is_superuser or user.is_staff) and not user.is_trainer)
    requested_stats_scope = (request.GET.get('stats_scope') or 'overall').lower()
    dashboard_stats_scope = requested_stats_scope if requested_stats_scope in {'overall', 'personal'} else 'overall'
    if not can_switch_dashboard_scope:
        dashboard_stats_scope = 'overall'

    if user.is_trainer and user.centre:
        device_query = Import.objects.filter(centre=user.centre)
        ppm_query = PPMTask.objects.filter(device__centre=user.centre)
        repair_query = DeviceRepair.objects.filter(device__centre=user.centre)
        incident_query = IncidentReport.objects.filter(reported_by=user)
        workplan_query = WorkPlan.objects.filter(user=user)
        asset_query = MissionCriticalAsset.objects.all()
        backup_query = BackupRegistry.objects.filter(centre=user.centre)
        user_scope = "centre"
    elif can_switch_dashboard_scope and dashboard_stats_scope == 'personal':
        device_query = Import.objects.filter(added_by=user)
        ppm_query = PPMTask.objects.filter(created_by=user)
        repair_query = DeviceRepair.objects.filter(created_by=user)
        incident_query = IncidentReport.objects.filter(reported_by=user)
        workplan_query = WorkPlan.objects.filter(user=user)
        asset_query = MissionCriticalAsset.objects.none()
        backup_query = BackupRegistry.objects.none()
        user_scope = "personal"
    elif user.is_superuser and not user.is_trainer:
        device_query = Import.objects.all()
        ppm_query = PPMTask.objects.all()
        repair_query = DeviceRepair.objects.all()
        incident_query = IncidentReport.objects.all()
        workplan_query = WorkPlan.objects.all()
        asset_query = MissionCriticalAsset.objects.all()
        backup_query = BackupRegistry.objects.all()
        user_scope = "all"
    elif user.is_staff and not user.is_trainer:
        device_query = Import.objects.all()
        ppm_query = PPMTask.objects.all()
        repair_query = DeviceRepair.objects.all()
        incident_query = IncidentReport.objects.all()
        workplan_query = WorkPlan.objects.all()
        asset_query = MissionCriticalAsset.objects.all()
        backup_query = BackupRegistry.objects.all()
        user_scope = "all"
    else:
        device_query = Import.objects.none()
        ppm_query = PPMTask.objects.none()
        repair_query = DeviceRepair.objects.none()
        incident_query = IncidentReport.objects.none()
        workplan_query = WorkPlan.objects.none()
        asset_query = MissionCriticalAsset.objects.none()
        backup_query = BackupRegistry.objects.none()
        user_scope = "none"

    active_period = PPMPeriod.objects.filter(is_active=True).first()

    total_devices = device_query.count()
    approved_devices = device_query.filter(is_approved=True, is_disposed=False).count()
    pending_approvals = device_query.filter(is_approved=False, is_disposed=False).count()
    disposed_devices = device_query.filter(is_disposed=True).count()
    active_device_query = device_query.filter(is_approved=True, is_disposed=False)

    # === NEW: Group by CATEGORY instead of parsing device_name string ===
    category_counts = (
        active_device_query
        .values('category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    devices_by_category = []
    category_display_map = dict(Import.CATEGORY_CHOICES)

    total_categorized = 0
    for item in category_counts:
        cat_value = item['category']
        if cat_value:
            label = category_display_map.get(cat_value, cat_value.replace('_', ' ').title())
            count = item['count']
            devices_by_category.append({'category': label, 'count': count})
            total_categorized += count

    # Add "Unknown" for devices with blank or null category
    unknown_count = (
        active_device_query.filter(category__isnull=True).count() +
        active_device_query.filter(category='').count()
    )
    if unknown_count > 0:
        devices_by_category.append({'category': 'Unknown', 'count': unknown_count})

    # Sort by count descending
    devices_by_category = sorted(devices_by_category, key=lambda x: x['count'], reverse=True)

    # Dashboard spotlight category counts (scope-aware because device_query is already scoped)
    laptop_count = active_device_query.filter(category='laptop').count() 
    desktop_count = active_device_query.filter(category='system_unit').count() 
    smart_phone_count = active_device_query.filter(category='smart_phone').count()
    desk_phone_count = active_device_query.filter(category='desk_phone').count()
    ipad_count = active_device_query.filter(category='ipad').count()
    tablet_count = active_device_query.filter(category='tablet').count()
    # Count only Starlink routers (exclude kits/dishes/etc.) 
    starlink_count = active_device_query.filter( 
        (Q(device_name__icontains='starlink') | Q(system_model__icontains='starlink')) & 
        (Q(device_name__icontains='router') | Q(system_model__icontains='router')) 
    ).count() 

    all_category_counts = []
    raw_category_map = {item['category']: item['count'] for item in category_counts if item['category']}
    for value, label in Import.CATEGORY_CHOICES:
        all_category_counts.append({
            'key': value,
            'label': label,
            'count': raw_category_map.get(value, 0),
        })
    if unknown_count:
        all_category_counts.append({'key': 'unknown', 'label': 'Unknown', 'count': unknown_count})

    # Keep dashboard chart clicks consistent with the default "Filtered Devices" view
    # (approved + not disposed, unless the user explicitly clears filters).
    device_status_breakdown = active_device_query.values('status').annotate(count=Count('id')).order_by('-count')
    device_condition_breakdown = device_query.filter(is_approved=True, is_disposed=False).values('device_condition').annotate(count=Count('id')).order_by('-count')

    all_centres = Centre.objects.all()
    devices_by_centre = []
    for centre in all_centres:
        count = device_query.filter(centre=centre, is_approved=True, is_disposed=False).count()
        if user_scope == "centre" and centre != user.centre:
            continue
        devices_by_centre.append({'centre__name': centre.name, 'count': count, 'centre_id': centre.id})
    devices_by_centre = sorted(devices_by_centre, key=lambda x: x['count'], reverse=True)

    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    recent_devices_count = device_query.filter(date__gte=thirty_days_ago).count()
    recent_devices = device_query.order_by('-date')[:10]

    total_repairs = repair_query.count()
    open_repairs_count = repair_query.filter(status=DeviceRepair.STATUS_IN_PROGRESS).count()
    repairs_last_30_days = repair_query.filter(date_of_repair__gte=thirty_days_ago).count()
    repair_status_breakdown = list(
        repair_query.values('status').annotate(count=Count('id')).order_by('status')
    )

    # PPM Logic remains unchanged...
    total_ppm_tasks = 0
    devices_with_ppm = 0
    devices_without_ppm = 0
    ppm_completion_rate = 0
    ppm_status_labels = []
    ppm_status_data = []
    ppm_status_colors = []
    ppm_tasks_by_activity = []
    ppm_by_centre = []
    period_name = None
    period_id = None

    if active_period:
        period = active_period
        is_active_period = True
    else:
        period = PPMPeriod.objects.order_by('-end_date').first()
        is_active_period = False

    if period:
        period_name = period.name
        period_id = period.id
        ppm_query_period = ppm_query.filter(period=period)
        total_ppm_tasks = ppm_query_period.count()
        devices_with_ppm = ppm_query_period.values('device').distinct().count()
        devices_without_ppm = approved_devices - devices_with_ppm
        ppm_completion_rate = round((devices_with_ppm / approved_devices * 100) if approved_devices > 0 else 0, 1)

        if is_active_period:
            ppm_status_labels = ['PPM Done', 'PPM Not Done']
            ppm_status_data = [devices_with_ppm, devices_without_ppm]
            ppm_status_colors = ['#10B981', '#F59E0B']
        else:
            ppm_status_labels = ['PPM Done', 'PPM Overdue']
            ppm_status_data = [devices_with_ppm, devices_without_ppm]
            ppm_status_colors = ['#10B981', '#EF4444']

        ppm_tasks_by_activity = ppm_query_period.values('activities__name').annotate(count=Count('id')).order_by('-count')

        ppm_by_centre = []
        for centre in all_centres:
            if user_scope == "centre" and centre != user.centre:
                continue
            centre_approved = device_query.filter(centre=centre, is_approved=True, is_disposed=False).count()
            centre_with_ppm = ppm_query_period.filter(device__centre=centre).values('device').distinct().count()
            ppm_by_centre.append({
                'device__centre__name': centre.name,
                'centre_id': centre.id,
                'total': centre_approved,
                'completed': centre_with_ppm
            })
        ppm_by_centre = sorted(ppm_by_centre, key=lambda x: x['completed'], reverse=True)

    overdue_ppm_tasks = ppm_query.filter(
        period__end_date__lt=timezone.now().date(),
        completed_date__isnull=True
    ).count()

    seven_days_ahead = timezone.now().date() + timedelta(days=7)
    tasks_due_soon = ppm_query.filter(
        period__end_date__lte=seven_days_ahead,
        period__end_date__gte=timezone.now().date(),
        completed_date__isnull=True
    ).count()

    recent_ppm_completions = ppm_query.filter(completed_date__isnull=False).order_by('-completed_date')[:5]

    total_users = CustomUser.objects.count() if user.is_superuser else 0
    active_users = CustomUser.objects.filter(is_active=True).count() if user.is_superuser else 0
    total_centres = Centre.objects.count() if user.is_superuser else 0
    pending_updates = PendingUpdate.objects.count() if user.is_superuser else (
        PendingUpdate.objects.filter(import_record__centre=user.centre).count() if user.centre else 0
    )

    sync_stale_workflow_notifications(user)
    notifications_qs = Notification.objects.filter(user=user).select_related('content_type', 'responded_by').order_by('is_read', '-created_at')
    notifications = notifications_qs[:5]
    unread_count = notifications_qs.filter(is_read=False).count()

    recent_incidents = incident_query.order_by('-date_of_report')[:5]
    open_incidents_count = incident_query.filter(status__in=['Open', 'In Progress']).count()

    today = timezone.now().date()
    current_work_plan = WorkPlan.objects.filter(user=user, week_start_date__lte=today, week_end_date__gte=today).first()
    trainers_query = CustomUser.objects.filter(is_active=True, is_trainer=True, is_superuser=False)
    if user_scope == "personal":
        trainers_query = CustomUser.objects.filter(pk=user.pk, is_active=True)
    elif user_scope == "centre" and user.centre:
        trainers_query = trainers_query.filter(centre=user.centre)
    total_trainers_count = trainers_query.count()

    team_work_plans = WorkPlan.objects.filter(
        week_start_date__lte=today,
        week_end_date__gte=today,
        user__is_active=True,
        user__is_trainer=True,
        user__is_superuser=False,
    )
    if user_scope == "personal":
        team_work_plans = WorkPlan.objects.filter(
            user=user,
            week_start_date__lte=today,
            week_end_date__gte=today,
        )
    elif user_scope == "centre" and user.centre:
        team_work_plans = team_work_plans.filter(user__centre=user.centre)
    submitted_work_plans = team_work_plans.values('user_id').distinct().count()

    # Work plan task status (current week) for dashboard chart
    current_week_workplan_tasks = WorkPlanTask.objects.filter(
        work_plan__week_start_date__lte=today,
        work_plan__week_end_date__gte=today,
    )
    if user_scope == "centre" and user.centre:
        current_week_workplan_tasks = current_week_workplan_tasks.filter(
            work_plan__user__centre=user.centre,
            work_plan__user__is_trainer=True,
        )
    elif user_scope == "personal":
        current_week_workplan_tasks = current_week_workplan_tasks.filter(work_plan__user=user)
    elif user_scope == "all":
        current_week_workplan_tasks = current_week_workplan_tasks.filter(work_plan__user__is_trainer=True)
    else:
        current_week_workplan_tasks = WorkPlanTask.objects.none()

    workplan_task_status_breakdown = list(
        current_week_workplan_tasks.values('status').annotate(count=Count('id')).order_by('status')
    )

    critical_assets_count = asset_query.count()
    asset_criticality_breakdown = asset_query.values('criticality_level').annotate(count=Count('id')).order_by('criticality_level')
    recent_backups = backup_query.order_by('-date')[:5]

    # Dashboard trends (last 6 months)
    trend_months = 6
    month_anchors = []
    current_month = today.replace(day=1)
    for _ in range(trend_months):
        month_anchors.append(current_month)
        prev_month_last_day = current_month - timedelta(days=1)
        current_month = prev_month_last_day.replace(day=1)
    month_anchors.reverse()

    month_labels = [m.strftime('%b %Y') for m in month_anchors]

    def _monthly_counts(qs, date_field):
        raw = (
            qs.annotate(month_bucket=TruncMonth(date_field))
              .values('month_bucket')
              .annotate(count=Count('id'))
              .order_by('month_bucket')
        )
        count_map = {}
        for item in raw:
            if item['month_bucket']:
                month_value = item['month_bucket']
                month_key = month_value.date() if hasattr(month_value, 'date') else month_value
                count_map[month_key] = item['count']
        return [count_map.get(anchor, 0) for anchor in month_anchors]

    devices_monthly = [
        {'month': label, 'count': count}
        for label, count in zip(month_labels, _monthly_counts(device_query, 'date'))
    ]
    ppm_completed_monthly = [
        {'month': label, 'count': count}
        for label, count in zip(month_labels, _monthly_counts(ppm_query.filter(completed_date__isnull=False), 'completed_date'))
    ]

    workplan_trend_query = WorkPlan.objects.filter(user__is_active=True, user__is_trainer=True, user__is_superuser=False)
    if user_scope == "personal":
        workplan_trend_query = WorkPlan.objects.filter(user=user)
    elif user_scope == "centre" and user.centre:
        workplan_trend_query = workplan_trend_query.filter(user__centre=user.centre)
    elif user_scope == "none":
        workplan_trend_query = WorkPlan.objects.none()

    workplans_monthly = [
        {'month': label, 'count': count}
        for label, count in zip(month_labels, _monthly_counts(workplan_trend_query, 'week_start_date'))
    ]
    incidents_monthly = [
        {'month': label, 'count': count}
        for label, count in zip(month_labels, _monthly_counts(incident_query, 'date_of_report'))
    ]
    repairs_monthly = [
        {'month': label, 'count': count}
        for label, count in zip(month_labels, _monthly_counts(repair_query, 'date_of_repair'))
    ]

    workplan_submission_pending = max(total_trainers_count - submitted_work_plans, 0)

    context = {
        'user_scope': user_scope,
        'dashboard_stats_scope': dashboard_stats_scope,
        'can_switch_dashboard_scope': can_switch_dashboard_scope,
        'can_download_inventory_centre_report': _can_download_inventory_centre_report(user),
        'total_devices': total_devices,
        'approved_devices': approved_devices,
        'pending_approvals': pending_approvals,
        'disposed_devices': disposed_devices,
        'total_repairs': total_repairs,
        'open_repairs_count': open_repairs_count,
        'repairs_last_30_days': repairs_last_30_days,
        'repair_status_breakdown': repair_status_breakdown,
        'recent_devices_count': recent_devices_count,
        'recent_devices': recent_devices,
        'device_status_breakdown': device_status_breakdown,
        'devices_by_centre': devices_by_centre,
        'devices_by_category': devices_by_category,  # ← Updated key
        'device_condition_breakdown': device_condition_breakdown, 
        'laptop_count': laptop_count, 
        'desktop_count': desktop_count, 
        'starlink_count': starlink_count, 
        'smart_phone_count': smart_phone_count,
        'desk_phone_count': desk_phone_count,
        'ipad_count': ipad_count,
        'tablet_count': tablet_count,
        'all_category_counts': all_category_counts, 
        'devices_monthly': devices_monthly, 
        'ppm_completed_monthly': ppm_completed_monthly, 
        'repairs_monthly': repairs_monthly,

        'total_ppm_tasks': total_ppm_tasks,
        'devices_with_ppm': devices_with_ppm,
        'devices_without_ppm': devices_without_ppm,
        'overdue_ppm_tasks': overdue_ppm_tasks,
        'tasks_due_soon': tasks_due_soon,
        'ppm_completion_rate': ppm_completion_rate,
        'ppm_tasks_by_activity': ppm_tasks_by_activity,
        'ppm_by_centre': ppm_by_centre,
        'recent_ppm_completions': recent_ppm_completions,
        'ppm_status_labels': ppm_status_labels,
        'ppm_status_data': ppm_status_data,
        'ppm_status_colors': ppm_status_colors,
        'period_name': period_name,
        'period_id': period_id,
        'is_active_period': is_active_period,

        'total_users': total_users,
        'active_users': active_users,
        'total_centres': total_centres,
        'pending_updates': pending_updates,

        'notifications': notifications,
        'unread_count': unread_count,

        'recent_incidents': recent_incidents,
        'open_incidents_count': open_incidents_count,
        'current_work_plan': current_work_plan,
        'total_staff_for_work_plans': total_trainers_count,
        'submitted_work_plans_count': submitted_work_plans,
        'total_trainers_count': total_trainers_count,
        'workplan_submission_pending': workplan_submission_pending,
        'workplan_task_status_breakdown': workplan_task_status_breakdown,
        'workplans_monthly': workplans_monthly,
        'incidents_monthly': incidents_monthly,
        'critical_assets_count': critical_assets_count,
        'asset_criticality_breakdown': asset_criticality_breakdown,
        'recent_backups': recent_backups,
    }
    # from itinventory import settings
    # if settings.DB_NAME_CONFIG == 'ufdxwals_it_test_db':
    #     template_name = 'index_test.html'
    # else:
    template_name = 'index.html'

    return render(request, template_name, context)


@login_required
@require_safe
def download_inventory_by_centre_report(request):
    if not _can_download_inventory_centre_report(request.user):
        return HttpResponseForbidden("Only IT managers can download this report.")

    devices = get_inventory_devices()
    workbook = build_inventory_workbook(devices, merge_centres=False)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    filename = f"IT_Inventory_All_Centres_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response


@login_required
def filtered_list_view(request, list_type): 
    user = request.user 
    params = request.GET 
    def _is_truthy(value):
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    user_scope = "none"
    if user.is_superuser:
        user_scope = "all"
    elif user.is_trainer and user.centre:
        user_scope = "centre"

    context = {
        'list_type': list_type,
        'page_title': f'Filtered List: {list_type.title()}',
        'user': user,
        'user_scope': user_scope,
        'params': params.urlencode(),
        'filters': params,
    }

    qs = None
    all_centres = Centre.objects.all().order_by('name')
    all_departments = Department.objects.all().order_by('name')

    if list_type == 'devices': 
        context['page_title'] = 'Filtered Devices'
        context['all_centres'] = all_centres
        context['all_departments'] = all_departments
        
        # NEW: Pass category choices directly from the model
        context['category_choices'] = Import.CATEGORY_CHOICES
        
        context['all_status'] = Import.objects.filter(is_approved=True).values_list('status', flat=True).distinct()
        context['all_conditions'] = Import.objects.filter(is_approved=True).values_list('device_condition', flat=True).distinct()

        if user_scope == "all":
            qs = Import.objects.all()
        elif user_scope == "centre":
            qs = Import.objects.filter(centre=user.centre)
        else:
            qs = Import.objects.none()

        clear = _is_truthy(params.get('clear'))
        filters = Q()

        # Approval filter (default: approved only unless "clear=1")
        if params.get('is_approved') is not None:
            filters &= Q(is_approved=_is_truthy(params.get('is_approved')))
        elif not clear:
            filters &= Q(is_approved=True)

        # Disposed filter (default: not disposed unless "clear=1")
        if params.get('is_disposed') is not None:
            filters &= Q(is_disposed=_is_truthy(params.get('is_disposed')))
        elif not clear:
            filters &= Q(is_disposed=False)

        # Centre filter
        if params.get('centre_id'):
            filters &= Q(centre_id=params.get('centre_id'))
        
        # Department filter
        if params.get('department_id'):
            filters &= Q(department_id=params.get('department_id'))
        
        # Status filter 
        if params.get('status'):
            if params.get('status') == 'Unknown':
                filters &= (Q(status__isnull=True) | Q(status=''))
            else:
                filters &= Q(status=params.get('status'))
         
        # Condition filter 
        if params.get('device_condition'):
            if params.get('device_condition') == 'Unknown':
                filters &= (Q(device_condition__isnull=True) | Q(device_condition=''))
            else:
                filters &= Q(device_condition=params.get('device_condition'))

        # Category filter (supports "unknown" from dashboard tiles)
        if params.get('category'):
            if params.get('category') == 'unknown':
                filters &= (Q(category__isnull=True) | Q(category=''))
            else:
                filters &= Q(category=params.get('category'))

        # Dashboard shortcut: Starlink routers only
        if _is_truthy(params.get('starlink_router')):
            filters &= (
                (Q(device_name__icontains='starlink') | Q(system_model__icontains='starlink')) &
                (Q(device_name__icontains='router') | Q(system_model__icontains='router'))
            )
        if _is_truthy(params.get('ipad')):
            filters &= (
                Q(category='ipad') |
                Q(device_name__icontains='ipad') |
                Q(system_model__icontains='ipad')
            )

        filtered_qs = qs.filter(filters).select_related('centre', 'department', 'assignee', 'assignee__centre', 'assignee__department').order_by('-pk')

        context['stats'] = {
            'total': filtered_qs.count(),
            'by_status': filtered_qs.values('status').annotate(count=Count('status')).order_by('-count'),
            'by_condition': filtered_qs.values('device_condition').annotate(count=Count('device_condition')).order_by('-count'),
        }

    elif list_type == 'ppm':
        context['page_title'] = 'Filtered PPM Tasks'
        context['all_centres'] = all_centres
        context['all_periods'] = PPMPeriod.objects.all().order_by('-start_date')

        if user_scope == "all":
            qs = PPMTask.objects.all()
        elif user_scope == "centre":
            qs = PPMTask.objects.filter(device__centre=user.centre)
        else:
            qs = PPMTask.objects.none()

        filters = Q()

        if params.get('centre_id'):
            filters &= Q(device__centre_id=params.get('centre_id'))
        if params.get('period_id'):
            filters &= Q(period_id=params.get('period_id'))
        if params.get('activity'):
            filters &= Q(activities__name=params.get('activity'))

        if params.get('ppm_status') == 'done':
            filters &= Q(completed_date__isnull=False)
        elif params.get('ppm_status') == 'pending':
            filters &= Q(completed_date__isnull=True, period__is_active=True)
        elif params.get('ppm_status') == 'overdue':
            filters &= Q(completed_date__isnull=True, period__end_date__lt=timezone.now().date())
        elif params.get('ppm_status') == 'due_soon':
            seven_days_ahead = timezone.now().date() + timedelta(days=7)
            filters &= Q(completed_date__isnull=True,
                         period__end_date__gte=timezone.now().date(),
                         period__end_date__lte=seven_days_ahead)

        filtered_qs = qs.filter(filters).distinct().order_by('period__name', 'device__serial_number')

        total_tasks = filtered_qs.count()
        completed = filtered_qs.filter(completed_date__isnull=False).count()
        pending = total_tasks - completed

        context['stats'] = {
            'total': total_tasks,
            'completed': completed,
            'pending': pending,
        }

    elif list_type == 'assets':
        context['page_title'] = 'Mission Critical Assets'
        context['all_criticality'] = [c[0] for c in MissionCriticalAsset.CRITICALITY_LEVEL_CHOICES]
        context['all_departments'] = all_departments

        qs = MissionCriticalAsset.objects.all()
        filters = Q()

        if params.get('department_id'):
            filters &= Q(department_id=params.get('department_id'))
        if params.get('criticality_level'):
            filters &= Q(criticality_level=params.get('criticality_level'))

        filtered_qs = qs.filter(filters).order_by('name')
        context['stats'] = {
            'total': filtered_qs.count(),
            'by_criticality': filtered_qs.values('criticality_level').annotate(count=Count('id')).order_by(),
        }

    elif list_type == 'incidents':
        context['page_title'] = 'Incident Reports'
        context['all_statuses'] = [s[0] for s in IncidentReport.STATUS_CHOICES]

        if user_scope == "all":
            qs = IncidentReport.objects.all()
        elif user_scope == "centre":
            qs = IncidentReport.objects.filter(reported_by=user)
        else:
            qs = IncidentReport.objects.none()

        filters = Q()
        if params.get('incident_number'):
            filters &= Q(incident_number=params.get('incident_number'))
        if params.get('status'):
            filters &= Q(status=params.get('status'))

        filtered_qs = qs.filter(filters).order_by('-date_of_report')
        context['stats'] = {
            'total': filtered_qs.count(),
            'by_status': filtered_qs.values('status').annotate(count=Count('id')).order_by(),
        }

    elif list_type == 'workplans':
        context['page_title'] = 'Work Plans'
        context['all_staff'] = CustomUser.objects.filter(is_active=True, is_trainer=True).order_by('username')

        if user_scope == "all":
            qs = WorkPlan.objects.all()
        elif user_scope == "centre":
            qs = WorkPlan.objects.filter(user=user)
        else:
            qs = Import.objects.none()

        filters = Q()
        if params.get('user_id'):
            filters &= Q(user_id=params.get('user_id'))
        if params.get('week') == 'current':
            today = timezone.now().date()
            filters &= Q(week_start_date__lte=today, week_end_date__gte=today)

        filtered_qs = qs.filter(filters).order_by('-week_start_date', 'user__username')
        context['stats'] = {
            'total': filtered_qs.count(),
            'users': filtered_qs.values('user__username').distinct().count()
        }

    else:
        raise Http404("Invalid list type specified.")

    paginator = Paginator(filtered_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context['page_obj'] = page_obj
    context['total_results'] = paginator.count
    context['is_paginated'] = page_obj.has_other_pages()

    return render(request, 'dashboard/filtering/master_list.html', context)
