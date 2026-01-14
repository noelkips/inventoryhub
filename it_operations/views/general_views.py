from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import datetime, timedelta, date
from django.db.models import Q, Count
from devices.models import Centre, Department
from ..models import (MissionCriticalAsset, BackupRegistry)
from django.contrib.auth import get_user_model
import calendar

User = get_user_model()

# ============ MISSION CRITICAL ASSETS VIEWS ============
@login_required
def mission_critical_list(request):
    """Display all mission critical assets"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to access Mission Critical Assets.")
        return redirect('dashboard')
    
    assets = MissionCriticalAsset.objects.all()
    
    category = request.GET.get('category')
    if category:
        assets = assets.filter(category=category)
    
    criticality = request.GET.get('criticality')
    if criticality:
        assets = assets.filter(criticality_level=criticality)
    
    search = request.GET.get('search')
    if search:
        assets = assets.filter(Q(name__icontains=search) | Q(notes__icontains=search))
    
    paginator = Paginator(assets, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'assets': page_obj.object_list,
        'categories': MissionCriticalAsset.CATEGORY_CHOICES,
        'criticality_levels': MissionCriticalAsset.CRITICALITY_LEVEL_CHOICES,
    }
    return render(request, 'it_operations/mission_critical/asset_list.html', context)


@login_required
def mission_critical_detail(request, pk):
    """Display asset details"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to access this.")
        return redirect('dashboard')
    
    asset = get_object_or_404(MissionCriticalAsset, pk=pk)
    context = {'asset': asset}
    return render(request, 'it_operations/mission_critical/asset_detail.html', context)


@login_required
def mission_critical_create(request):
    """Create a new mission critical asset"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to create assets.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        asset = MissionCriticalAsset(
            name=request.POST.get('name'),
            category=request.POST.get('category'),
            location_scope=request.POST.get('location_scope'),
            purpose_function=request.POST.get('purpose_function'),
            dependency_linked_system=request.POST.get('dependency_linked_system'),
            backup_recovery_method=request.POST.get('backup_recovery_method'),
            department_id=request.POST.get('department'),
            criticality_level=request.POST.get('criticality_level'),
            notes=request.POST.get('notes'),
            created_by=request.user
        )
        asset.save()
        messages.success(request, 'Mission Critical Asset created successfully!')
        return redirect('mission_critical_list')
    
    departments = Department.objects.all()
    context = {
        'action': 'Add',
        'departments': departments,
        'categories': MissionCriticalAsset.CATEGORY_CHOICES,
        'criticality_levels': MissionCriticalAsset.CRITICALITY_LEVEL_CHOICES,
    }
    return render(request, 'it_operations/mission_critical/asset_form.html', context)


@login_required
def mission_critical_update(request, pk):
    """Update a mission critical asset"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to update assets.")
        return redirect('dashboard')
    
    asset = get_object_or_404(MissionCriticalAsset, pk=pk)
    
    if request.method == 'POST':
        asset.name = request.POST.get('name')
        asset.category = request.POST.get('category')
        asset.location_scope = request.POST.get('location_scope')
        asset.purpose_function = request.POST.get('purpose_function')
        asset.dependency_linked_system = request.POST.get('dependency_linked_system')
        asset.backup_recovery_method = request.POST.get('backup_recovery_method')
        asset.department_id = request.POST.get('department')
        asset.criticality_level = request.POST.get('criticality_level')
        asset.notes = request.POST.get('notes')
        asset.save()
        messages.success(request, 'Mission Critical Asset updated successfully!')
        return redirect('mission_critical_detail', pk=asset.pk)
    
    departments = Department.objects.all()
    context = {
        'asset': asset,
        'action': 'Update',
        'departments': departments,
        'categories': MissionCriticalAsset.CATEGORY_CHOICES,
        'criticality_levels': MissionCriticalAsset.CRITICALITY_LEVEL_CHOICES,
    }
    return render(request, 'it_operations/mission_critical/asset_form.html', context)


@login_required
def mission_critical_delete(request, pk):
    """Delete confirmation for mission critical asset"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to delete assets.")
        return redirect('dashboard')
    
    asset = get_object_or_404(MissionCriticalAsset, pk=pk)
    
    if request.method == 'POST':
        asset.delete()
        messages.success(request, 'Mission Critical Asset deleted successfully!')
        return redirect('mission_critical_list')
    
    context = {'asset': asset}
    return render(request, 'it_operations/mission_critical/asset_confirm_delete.html', context)


# ============ BACKUP REGISTRY VIEWS ============
@login_required
def backup_registry_list(request):
    """Display all backup records with reports"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to access Backup Registry.")
        return redirect('dashboard')
    
    backups = BackupRegistry.objects.all()
    
    centre = request.GET.get('centre')
    if centre:
        backups = backups.filter(centre_id=centre)
    
    system = request.GET.get('system')
    if system:
        backups = backups.filter(system=system)
    
    # Get statistics
    total_backups = backups.count()
    backups_by_system = backups.values('system').annotate(count=Count('id')).order_by('-count')
    backups_by_centre = backups.values('centre__name').annotate(count=Count('id')).order_by('-count')
    
    paginator = Paginator(backups, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    centres = Centre.objects.all()
    context = {
        'page_obj': page_obj,
        'backups': page_obj.object_list,
        'centres': centres,
        'system_choices': BackupRegistry.SYSTEM_CHOICES,
        'total_backups': total_backups,
        'backups_by_system': backups_by_system,
        'backups_by_centre': backups_by_centre,
    }
    return render(request, 'it_operations/backup_registry/backup_list.html', context)


@login_required
def backup_registry_create(request):
    """Create a new backup record"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to create backup records.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        backup = BackupRegistry(
            system=request.POST.get('system'),
            centre_id=request.POST.get('centre'),
            done_by=request.user,
            comments=request.POST.get('comments')
        )
        backup.save()
        messages.success(request, 'Backup record created successfully!')
        return redirect('backup_registry_list')
    
    centres = Centre.objects.all()
    context = {
        'action': 'Add',
        'centres': centres,
        'system_choices': BackupRegistry.SYSTEM_CHOICES,
    }
    return render(request, 'it_operations/backup_registry/backup_form.html', context)


@login_required
def backup_registry_update(request, pk):
    """Update a backup record"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to update backup records.")
        return redirect('dashboard')
    
    backup = get_object_or_404(BackupRegistry, pk=pk)
    
    if request.method == 'POST':
        backup.system = request.POST.get('system')
        backup.centre_id = request.POST.get('centre')
        backup.comments = request.POST.get('comments')
        backup.save()
        messages.success(request, 'Backup record updated successfully!')
        return redirect('backup_registry_list')
    
    centres = Centre.objects.all()
    context = {
        'backup': backup,
        'action': 'Update',
        'centres': centres,
        'system_choices': BackupRegistry.SYSTEM_CHOICES,
    }
    return render(request, 'it_operations/backup_registry/backup_form.html', context)


@login_required
def backup_registry_delete(request, pk):
    """Delete confirmation for backup record"""
    if request.user.is_trainer:
        messages.error(request, "You do not have permission to delete backup records.")
        return redirect('dashboard')
    
    backup = get_object_or_404(BackupRegistry, pk=pk)
    
    if request.method == 'POST':
        backup.delete()
        messages.success(request, 'Backup record deleted successfully!')
        return redirect('backup_registry_list')
    
    context = {'backup': backup}
    return render(request, 'it_operations/backup_registry/backup_confirm_delete.html', context)

