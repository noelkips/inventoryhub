from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import PPMActivity, PPMPeriod, PPMTask

User = get_user_model()

class PPMPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active',)
    filter_horizontal = ('activities',)  # Checkbox-based multi-select for activities
    fieldsets = (
        (None, {
            'fields': ('name', 'start_date', 'end_date', 'is_active')
        }),
        ('Activities', {
            'fields': ('activities',)
        }),
    )

    def has_view_or_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

class PPMActivityAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

    def has_view_or_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

class PPMTaskAdmin(admin.ModelAdmin):
    list_display = ('device', 'period', 'get_activities', 'completed_date', 'created_by')
    list_filter = ('period', 'completed_date')
    search_fields = ('device__serial_number', 'activities__name')

    def get_activities(self, obj):
        return ", ".join([activity.name for activity in obj.activities.all()])
    get_activities.short_description = 'Activities'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

admin.site.register(PPMActivity, PPMActivityAdmin)
admin.site.register(PPMPeriod, PPMPeriodAdmin)
admin.site.register(PPMTask, PPMTaskAdmin)

admin.site.site_header = 'Mohi IT Inventory'
admin.site.site_title = 'Mohi IT Inventory'
admin.site.index_title = 'Mohi IT Inventory'