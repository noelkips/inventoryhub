from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.urls import reverse
from django.shortcuts import redirect
from django.db import transaction
from django import forms
from django.contrib.auth.models import Group

from .views import handle_uploaded_file
from .models import CustomUser, Import, Centre, Report
from .forms import ImportForm
from django.core.files.uploadedfile import SimpleUploadedFile
from io import BytesIO
import os

class CustomUserAdminForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
        required=False,
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput,
        required=False,
    )

    class Meta:
        model = CustomUser
        fields = '__all__'
        widgets = {
            'groups': forms.SelectMultiple(attrs={'class': 'select2'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        is_trainer = cleaned_data.get("is_trainer")
        centre = cleaned_data.get("centre")

        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError("Passwords do not match.")
        if is_trainer and not centre:
            raise forms.ValidationError("Centre is required for trainers.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password1 = self.cleaned_data.get("password1")
        if password1:
            user.set_password(password1)
        if commit:
            user.save()
            if hasattr(self, 'save_m2m'):
                user.groups.clear()
                groups = self.cleaned_data.get('groups')
                if groups is not None:
                    user.groups.set(groups)
        return user

class CustomUserAdmin(admin.ModelAdmin):
    form = CustomUserAdminForm
    list_display = ('username', 'email', 'is_trainer', 'centre', 'is_staff', 'is_superuser', 'get_groups')
    list_filter = ('is_trainer', 'centre', 'groups', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'groups__name')
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password1', 'password2')}),
        ('Personal Info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_trainer', 'centre', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'is_trainer','is_superuser', 'centre', 'groups'),
        }),
    )

    def get_fieldsets(self, request, obj=None):
        if not obj:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)

    def get_groups(self, obj):
        return ", ".join([group.name for group in obj.groups.all()])
    get_groups.short_description = 'Groups'

    def save_model(self, request, obj, form, change):
        if not change and form.cleaned_data.get('password1'):
            obj.set_password(form.cleaned_data['password1'])
        super().save_model(request, obj, form, change)

class ImportAdmin(admin.ModelAdmin):
    form = ImportForm
    list_display = (
        'centre', 'department', 'hardware', 'system_model', 'processor', 'ram_gb',
        'hdd_gb', 'serial_number', 'assignee_first_name', 'assignee_last_name',
        'assignee_email_address', 'device_condition', 'status', 'added_by',
        'approved_by', 'is_approved', 'reason_for_update'
    )
    search_fields = (
        'centre__centre_code', 'department', 'hardware', 'system_model', 'processor',
        'ram_gb', 'hdd_gb', 'serial_number', 'assignee_first_name', 'assignee_last_name',
        'assignee_email_address', 'device_condition', 'status', 'added_by__username',
        'approved_by__username', 'reason_for_update'
    )
    list_filter = (
        'centre', 'department', 'hardware', 'device_condition', 'status',
        'added_by', 'approved_by', 'is_approved'
    )
    readonly_fields = ('date', 'added_by')
    fieldsets = (
        (None, {
            'fields': (
                'file', 'centre', 'department', 'hardware', 'system_model', 'processor',
                'ram_gb', 'hdd_gb', 'serial_number', 'assignee_first_name', 'assignee_last_name',
                'assignee_email_address', 'device_condition', 'status', 'date', 'added_by',
                'approved_by', 'is_approved', 'reason_for_update'
            )
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = super().get_readonly_fields(request, obj)
        if request.user.is_trainer:
            readonly += ('is_approved', 'approved_by', 'centre')
        return readonly

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_trainer and not request.user.is_superuser:
            qs = qs.filter(centre=request.user.centre)
        return qs

    def save_model(self, request, obj, form, change):
        if not obj.added_by:
            obj.added_by = request.user
        if request.user.is_trainer and not request.user.is_superuser:
            obj.centre = request.user.centre
            obj.is_approved = False
        elif request.user.is_staff and form.cleaned_data.get('is_approved'):
            obj.approved_by = request.user
        if 'file' in form.cleaned_data and form.cleaned_data['file']:
            try:
                with transaction.atomic():
                    upload_dir = os.path.join(settings.MEDIA_ROOT, 'Uploads')
                    os.makedirs(upload_dir, exist_ok=True)
                    file_path = os.path.join(upload_dir, form.cleaned_data['file'].name)
                    with open(file_path, 'wb') as destination:
                        for chunk in form.cleaned_data['file'].chunks():
                            destination.write(chunk)
                    file_content = BytesIO()
                    for chunk in form.cleaned_data['file'].chunks():
                        file_content.write(chunk)
                    file_content.seek(0)
                    upload_file = SimpleUploadedFile(
                        form.cleaned_data['file'].name,
                        file_content.read(),
                        content_type=form.cleaned_data['file'].content_type
                    )
                    handle_uploaded_file(upload_file, request.user)
                    messages.success(request, "CSV file uploaded and data imported successfully.")
            except Exception as e:
                messages.error(request, f"Error processing CSV file: {str(e)}")
        else:
            try:
                with transaction.atomic():
                    if request.user.is_trainer and change and not form.cleaned_data.get('reason_for_update'):
                        messages.error(request, "Reason for update is required.")
                        return
                    super().save_model(request, obj, form, change)
                    messages.success(request, "Record saved successfully.")
            except Exception as e:
                messages.error(request, f"Error saving record: {str(e)}")

class ReportAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        displaycsv_url = reverse('import_displaycsv')
        return redirect(displaycsv_url)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        displaycsv_url = reverse('import_displaycsv')
        return redirect(displaycsv_url)

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Centre)
admin.site.register(Import, ImportAdmin)
admin.site.register(Report, ReportAdmin)