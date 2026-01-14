from django.contrib import admin
from .models import (
    MissionCriticalAsset, 
    BackupRegistry, 
    WorkPlan, 
    WorkPlanTask, 
    PublicHoliday, 
    IncidentReport
)

# ============ MISSION CRITICAL ASSETS ============
@admin.register(MissionCriticalAsset)
class MissionCriticalAssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'criticality_level', 'department', 'created_at')
    list_filter = ('category', 'criticality_level', 'department', 'created_at')
    search_fields = ('name', 'notes', 'purpose_function')
    readonly_fields = ('created_by', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category', 'criticality_level')
        }),
        ('Details', {
            'fields': ('location_scope', 'purpose_function', 'dependency_linked_system', 'backup_recovery_method')
        }),
        ('Organization', {
            'fields': ('department',)
        }),
        ('Additional', {
            'fields': ('notes',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ============ BACKUP REGISTRY ============
@admin.register(BackupRegistry)
class BackupRegistryAdmin(admin.ModelAdmin):
    list_display = ('system', 'centre', 'date', 'done_by')
    list_filter = ('centre', 'date', 'done_by')
    search_fields = ('system', 'comments')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Backup Information', {
            'fields': ('system', 'centre', 'date', 'done_by')
        }),
        ('Details', {
            'fields': ('comments',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ============ WORK PLANS ============

class WorkPlanTaskInline(admin.TabularInline):
    model = WorkPlanTask
    extra = 1
    fields = ('date', 'task_name', 'status', 'is_leave', 'centre', 'department')
    show_change_link = True

@admin.register(WorkPlan)
class WorkPlanAdmin(admin.ModelAdmin):
    list_display = ('user', 'week_start_date', 'week_end_date', 'task_count', 'created_at')
    list_filter = ('week_start_date', 'user')
    # This search_fields is REQUIRED for WorkPlanTaskAdmin to use autocomplete_fields=['work_plan']
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    inlines = [WorkPlanTaskInline]
    readonly_fields = ('created_at', 'updated_at')

    def task_count(self, obj):
        return obj.tasks.count()
    task_count.short_description = 'Tasks'


@admin.register(WorkPlanTask)
class WorkPlanTaskAdmin(admin.ModelAdmin):
    list_display = ('task_name', 'get_user', 'date', 'status', 'is_leave', 'centre')
    list_filter = ('status', 'is_leave', 'date', 'work_plan__user')
    search_fields = ('task_name', 'work_plan__user__username')
    
    # FIXED: Removed 'centre', 'department', 'collaborators' to prevent E040 error
    # Only 'work_plan' is kept because WorkPlanAdmin (above) has search_fields defined.
    autocomplete_fields = ['work_plan']
    
    # Added this to make selecting multiple collaborators easier
    filter_horizontal = ('collaborators',)
    
    def get_user(self, obj):
        return obj.work_plan.user
    get_user.short_description = 'Owner'


# ============ UTILITIES ============
@admin.register(PublicHoliday)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ('name', 'date')
    ordering = ('date',)


# ============ INCIDENT REPORTS ============
@admin.register(IncidentReport)
class IncidentReportAdmin(admin.ModelAdmin):
    list_display = ('incident_number', 'incident_type', 'date_of_incident', 'reported_by', 'status')
    list_filter = ('status', 'date_of_incident', 'incident_type')
    search_fields = ('incident_number', 'description', 'location')
    readonly_fields = ('date_of_report', 'incident_number')
    
    # Use filter_horizontal for collaborators here too if you want
    filter_horizontal = ('collaborators',)
    
    fieldsets = (
        ('Report Info', {
            'fields': ('incident_number', 'status', 'reported_by', 'reporter_title_role', 'collaborators')
        }),
        ('Incident Details', {
            'fields': ('incident_type', 'date_of_incident', 'location', 'specific_area')
        }),
        ('Narrative', {
            'fields': ('description', 'parties_involved', 'witnesses')
        }),
        ('Action Taken', {
            'fields': ('immediate_actions_taken', 'reported_to', 'follow_up_actions_required')
        }),
    )