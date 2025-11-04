from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.urls import reverse
from django.shortcuts import redirect
from django.db import transaction
from django import forms
from django.contrib.auth.models import Group
from django.utils.html import format_html
from django.shortcuts import get_object_or_404
from .views import handle_uploaded_file
from .models import CustomUser, Department, Import, Centre, Report
from .forms import ImportForm
from django.core.files.uploadedfile import SimpleUploadedFile
from io import BytesIO
import os

# admin.py
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _


# ----------------------------------------------------------------------
# 1. FORM – password + trainer-centre validation
# ----------------------------------------------------------------------
class CustomUserAdminForm(forms.ModelForm):
    password1 = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput,
        required=False,
        help_text=_("Leave blank to keep current password."),
    )
    password2 = forms.CharField(
        label=_("Confirm Password"),
        widget=forms.PasswordInput,
        required=False,
    )

    class Meta:
        model = CustomUser
        fields = '__all__'
        widgets = {
            'groups': forms.SelectMultiple(attrs={'class': "select2"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password1")
        p2 = cleaned_data.get("password2")
        is_trainer = cleaned_data.get("is_trainer")
        centre = cleaned_data.get("centre")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError(_("Passwords do not match."))

        if is_trainer and not centre:
            raise forms.ValidationError(_("Centre is required for trainers."))

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        p1 = self.cleaned_data.get("password1")
        if p1:
            user.set_password(p1)
        if commit:
            user.save()
            self.save_m2m()
        return user


# ----------------------------------------------------------------------
# 2. ADMIN – role-field protection + password fix
# ----------------------------------------------------------------------
@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    form = CustomUserAdminForm

    # ----- list view -----
    list_display = (
        "username", "email", "first_name", "last_name", "centre",
        "is_trainer", "is_staff", "is_superuser", "get_groups"
    )
    list_filter = ("is_trainer", "centre", "groups", "is_staff", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name", "groups__name")

    # ----- fieldsets (NO password1/2 here!) -----
    base_fieldsets = (
        (None, {"fields": ("username", "email")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "centre")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_trainer",
                    "is_staff",
                    "is_superuser",
                    "is_it_manager",
                    "is_senior_it_officer",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username", "email", "password1", "password2",
                    "first_name", "last_name", "centre",
                    "is_trainer", "is_staff", "is_superuser",
                    "is_it_manager", "is_senior_it_officer", "groups",
                ),
            },
        ),
    )

    def get_groups(self, obj):
        return ", ".join(g.name for g in obj.groups.all())
    get_groups.short_description = "Groups"

    # ------------------------------------------------------------------
    # 3. DYNAMIC FORM + PASSWORD FIELDS
    # ------------------------------------------------------------------
    def get_form(self, request, obj=None, **kwargs):
        """
        Inject password1/password2 into the form for both add & change.
        """
        form = super().get_form(request, obj, **kwargs)
        return form

    def get_fieldsets(self, request, obj=None):
        if obj is None:  # Add form
            if self._is_role_editor(request):
                return self.add_fieldsets
            else:
                # Non-role editors: remove role fields from add form
                return (
                    (
                        None,
                        {
                            "classes": ("wide",),
                            "fields": (
                                "username", "email", "password1", "password2",
                                "first_name", "last_name", "centre",
                            ),
                        },
                    ),
                )
        return self.base_fieldsets

    # ------------------------------------------------------------------
    # 4. ROLE EDITOR CHECK
    # ------------------------------------------------------------------
    def _is_role_editor(self, request):
        return request.user.is_it_manager or request.user.is_senior_it_officer

    def get_readonly_fields(self, request, obj=None):
        readonly = super().get_readonly_fields(request, obj)

        if not self._is_role_editor(request):
            role_fields = (
                "is_trainer", "is_staff", "is_superuser",
                "is_it_manager", "is_senior_it_officer",
                "groups", "user_permissions"
            )
            readonly = readonly + role_fields

        # Never show password fields as readonly (they're not model fields)
        return readonly

    # ------------------------------------------------------------------
    # 5. BLOCK ROLE CHANGES
    # ------------------------------------------------------------------
    def save_model(self, request, obj, form, change):
        if not self._is_role_editor(request):
            role_keys = {
                "is_trainer", "is_staff", "is_superuser",
                "is_it_manager", "is_senior_it_officer",
                "groups", "user_permissions"
            }
            for key in role_keys:
                if key in form.cleaned_data:
                    db_val = getattr(CustomUser.objects.get(pk=obj.pk), key) if change else None
                    new_val = form.cleaned_data[key]
                    if key == "groups":
                        db_ids = {g.id for g in (obj.groups.all() if change else [])}
                        new_ids = {g.id for g in new_val} if new_val else set()
                        if db_ids != new_ids:
                            raise PermissionDenied("You are not allowed to modify user roles.")
                    elif db_val != new_val:
                        raise PermissionDenied("You are not allowed to modify user roles.")

        # Handle password
        p1 = form.cleaned_data.get("password1")
        if p1:
            obj.set_password(p1)

        super().save_model(request, obj, form, change)

    # ------------------------------------------------------------------
    # 6. WARNING MESSAGE
    # ------------------------------------------------------------------
    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self._is_role_editor(request):
            self.message_user(
                request,
                "You can only edit basic user information. Role changes are restricted.",
                level="warning",
            )
        return super().change_view(request, object_id, form_url, extra_context)

        
class ImportAdmin(admin.ModelAdmin):
    form = ImportForm
    list_display = (
        'get_centre', 'department', 'hardware', 'system_model', 'processor', 'ram_gb',
        'hdd_gb', 'serial_number', 'assignee_first_name', 'assignee_last_name',
        'assignee_email_address', 'device_condition', 'status', 'get_added_by',
        'get_approved_by', 'is_approved', 'reason_for_update'
    )
    search_fields = (
        'centre__name', 'department__name', 'hardware', 'system_model', 'processor',
        'ram_gb', 'hdd_gb', 'serial_number', 'assignee_first_name', 'assignee_last_name',
        'assignee_email_address', 'device_condition', 'status', 'added_by__username',
        'approved_by__username', 'reason_for_update'
    )
    list_filter = (
        ('centre', admin.RelatedOnlyFieldListFilter),
        ('added_by', admin.RelatedOnlyFieldListFilter),
        ('approved_by', admin.RelatedOnlyFieldListFilter),
        'is_approved'
    )
    readonly_fields = ()
    fieldsets = (
        (None, {
            'fields': (
                'file', 'centre', 'department', 'hardware', 'system_model', 'processor',
                'ram_gb', 'hdd_gb', 'serial_number', 'assignee_first_name', 'assignee_last_name',
                'assignee_email_address', 'device_condition', 'status', 'added_by',
                'approved_by', 'is_approved', 'reason_for_update'
            )
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = []
        if request.user.is_trainer:
            readonly = ['is_approved', 'approved_by', 'centre', 'file']
        return readonly

    def has_add_permission(self, request):
        return not request.user.is_trainer

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
        elif request.user.is_superuser and form.cleaned_data.get('is_approved'):
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

    def approve_selected_imports(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Only administrators can approve imports.", level=messages.ERROR)
            return
        approved_count = queryset.update(is_approved=True, approved_by=request.user)
        self.message_user(request, f"{approved_count} import(s) were successfully approved.")
    approve_selected_imports.short_description = "Approve selected imports"

    def delete_selected_imports(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Only administrators can delete imports.", level=messages.ERROR)
            return
        deleted_count = queryset.delete()[0]  # [0] gives the total number of deleted objects
        self.message_user(request, f"{deleted_count} import(s) were successfully deleted.")
    delete_selected_imports.short_description = "Delete selected imports"

    actions = ['approve_selected_imports', 'delete_selected_imports']
    # Override get_actions to remove the default 'delete_selected' action
    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def get_list_display(self, request):
        list_display = list(super().get_list_display(request))
        return tuple(list_display)  # Use default Django selection checkbox

    def get_row_actions(self, obj):
        return "-"  # Ensure no row-level buttons
    get_row_actions.allow_tags = True
    get_row_actions.short_description = 'Actions'

    def has_change_permission(self, request, obj=None):
        if request.user.is_trainer and obj and obj.is_approved:
            return False
        return super().has_change_permission(request, obj)

    def changelist_view(self, request, extra_context=None):
        self.request = request  # Store request for use in get_row_actions
        return super().changelist_view(request, extra_context)

    # Custom methods for list_display
    def get_centre(self, obj):
        return obj.centre.centre_code if obj.centre else "N/A"
    get_centre.short_description = 'Centre'

    def get_added_by(self, obj):
        return obj.added_by.username if obj.added_by else "N/A"
    get_added_by.short_description = 'Added By'

    def get_approved_by(self, obj):
        return obj.approved_by.username if obj.approved_by else "N/A"
    get_approved_by.short_description = 'Approved By'
class ReportAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False  # Remove the "Add" button for Report

    def changelist_view(self, request, extra_context=None):
        displaycsv_url = reverse('display_approved_imports')
        return redirect(displaycsv_url)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        displaycsv_url = reverse('display_approved_imports')
        return redirect(displaycsv_url)

admin.site.register(Centre)
admin.site.register(Department)
admin.site.register(Import, ImportAdmin)
admin.site.register(Report, ReportAdmin)