from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Centre, Book, Student


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'first_name', 'last_name', 'is_staff', 'is_librarian', 'is_student', 'centre']
    list_filter = ['is_staff', 'is_superuser', 'is_librarian', 'is_student', 'is_teacher', 'is_site_admin']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'centre')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Roles', {'fields': ('is_librarian', 'is_student', 'is_teacher', 'is_site_admin', 'is_other')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_staff', 'is_superuser')}
        ),
    )
    search_fields = ['email', 'first_name', 'last_name']
    ordering = ['email']


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Centre)
admin.site.register(Book)
admin.site.register(Student)
