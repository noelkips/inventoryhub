from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.urls import reverse
from django.shortcuts import redirect
from django.db import transaction
from .models import Import, Report
from .forms import ImportForm
from .views import handle_uploaded_file
from django.core.files.uploadedfile import SimpleUploadedFile
from io import BytesIO
import os

class ImportAdmin(admin.ModelAdmin):
    form = ImportForm
    list_display = (
        'centre','department', 'hardware', 'system_model', 'processor', 'ram_gb',
        'hdd_gb', 'serial_number', 'assignee_first_name', 'assignee_last_name',
        'assignee_email_address', 'device_condition', 'status', 'date'
    )
    search_fields = (
        'centre','department', 'hardware', 'system_model', 'processor', 'ram_gb',
        'hdd_gb', 'serial_number', 'assignee_first_name', 'assignee_last_name',
        'assignee_email_address', 'device_condition', 'status', 'date'
    )
    list_filter = ('centre','department', 'hardware', 'system_model', 'processor', 'ram_gb',
                    'hdd_gb', 'serial_number', 'assignee_first_name', 'assignee_last_name', 
                    'assignee_email_address', 'device_condition', 'status', 'date')

    def save_model(self, request, obj, form, change):
        print("Processing file in ImportAdmin save_model")
        if 'file' in form.cleaned_data and form.cleaned_data['file']:
            try:
                with transaction.atomic():
                    # Save file to disk without creating an Import instance
                    upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads')
                    os.makedirs(upload_dir, exist_ok=True)
                    file_path = os.path.join(upload_dir, form.cleaned_data['file'].name)
                    with open(file_path, 'wb') as destination:
                        for chunk in form.cleaned_data['file'].chunks():
                            destination.write(chunk)
                    # Create UploadedFile for CSV processing
                    file_content = BytesIO()
                    for chunk in form.cleaned_data['file'].chunks():
                        file_content.write(chunk)
                    file_content.seek(0)
                    upload_file = SimpleUploadedFile(
                        form.cleaned_data['file'].name,
                        file_content.read(),
                        content_type=form.cleaned_data['file'].content_type
                    )
                    # Process CSV data
                    handle_uploaded_file(upload_file)
                    messages.success(request, "CSV file uploaded and data imported successfully.")
            except Exception as e:
                messages.error(request, f"Error processing CSV file: {str(e)}")
        else:
            # Handle manual record creation/editing
            try:
                with transaction.atomic():
                    super().save_model(request, obj, form, change)
                    messages.success(request, "Record saved successfully.")
            except Exception as e:
                messages.error(request, f"Error saving record: {str(e)}")

admin.site.register(Import, ImportAdmin)

class ReportAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        displaycsv_url = reverse('import_displaycsv')
        return redirect(displaycsv_url)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        displaycsv_url = reverse('import_displaycsv')
        return redirect(displaycsv_url)

admin.site.register(Report, ReportAdmin)