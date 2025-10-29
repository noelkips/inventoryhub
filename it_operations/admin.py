from django.contrib import admin
from .models import MissionCriticalAsset, BackupRegistry, WorkPlan, WorkPlanActivity, WorkPlanComment

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


@admin.register(WorkPlan)
class WorkPlanAdmin(admin.ModelAdmin):
    list_display = ('user', 'week_start_date', 'week_end_date', 'created_at')
    list_filter = ('user', 'week_start_date')
    search_fields = ('user__username',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WorkPlanActivity)
class WorkPlanActivityAdmin(admin.ModelAdmin):
    list_display = ('work_plan', 'day', 'status', 'activity')
    list_filter = ('day', 'status', 'work_plan__week_start_date')
    search_fields = ('activity', 'work_plan__user__username')


@admin.register(WorkPlanComment)
class WorkPlanCommentAdmin(admin.ModelAdmin):
    list_display = ('work_plan', 'user', 'created_at')
    list_filter = ('created_at', 'user')
    search_fields = ('comment', 'work_plan__user__username')
    readonly_fields = ('created_at',)
