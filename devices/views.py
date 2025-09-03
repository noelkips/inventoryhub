from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction

from devices.forms import ClearanceForm

from .models import CustomUser, Import, Centre, Notification, PendingUpdate, Department
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from reportlab.pdfgen import canvas
from django.http import HttpResponse, HttpResponseForbidden
import openpyxl
from django.template.loader import get_template
from xhtml2pdf import pisa
from io import BytesIO, TextIOWrapper
import os, re
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import logout, update_session_auth_hash
import csv
from django.contrib.auth.models import Group, Permission
from django.urls import reverse
import gc
from django.utils import timezone
from django.contrib.auth import authenticate, login
import logging
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT
from django.contrib.contenttypes.models import ContentType

from django.http import HttpResponseRedirect
from django.template.loader import render_to_string

# Set up logging for debugging
logger = logging.getLogger(__name__)

def handle_uploaded_file(file, user):
    header_mapping = {
        'centre_code': 'centre_code',
        'department': 'department_code',
        'hardware': 'hardware',
        'system_model': 'system_model',
        'processor': 'processor',
        'ram_gb': 'ram_gb',
        'hdd_gb': 'hdd_gb',
        'serial_number': 'serial_number',
        'assignee_first_name': 'assignee_first_name',
        'assignee_last_name': 'assignee_last_name',
        'assignee_email_address': 'assignee_email_address',
        'device_condition': 'device_condition',
        'status': 'status',
        'date': 'date',
    }

    try:
        file.seek(0)
        decoded_file = TextIOWrapper(file.file, encoding='utf-8-sig')
        reader = csv.reader(decoded_file)
        headers = next(reader, None)
        if not headers:
            raise ValueError("CSV file is empty or invalid.")

        headers = [h.lower().strip() for h in headers]
        print(f"Headers: {headers}")

        # Check for required headers
        if 'centre_code' not in headers:
            raise ValueError("Missing required header: centre_code")
        if 'department_code' not in headers:
            raise ValueError("Missing required header: department")

        centre_code_index = headers.index('centre_code')
        import_instances = []

        for row in reader:
            print(f"Row: {row}")
            if not any(row):  # Skip empty rows
                print("Skipping empty row")
                continue
            serial_number = [value.strip() for header, value in zip(headers, row) if header == 'serial_number']
            if serial_number and Import.objects.filter(serial_number=serial_number[0]).exists():
                print(f"Skipping duplicate serial_number: {serial_number[0]}")
                continue
            import_instance = Import(added_by=user)
            centre_code = row[centre_code_index].strip() if centre_code_index < len(row) else None
            if centre_code:
                try:
                    centre = Centre.objects.get(centre_code=centre_code)
                    # Validate centre_code for trainers (not superusers)
                    if user.is_trainer and not user.is_superuser and user.centre and centre != user.centre:
                        raise ValueError("Import failed, you are only allowed to add devices belonging to your center.")
                    import_instance.centre = centre
                    print(f"Mapped centre_code {centre_code} to Centre: {centre.name}")
                except Centre.DoesNotExist:
                    print(f"Centre with centre_code {centre_code} not found, setting to None")
                    import_instance.centre = None
            for header, value in zip(headers, row):
                value = value.strip()
                field_name = header_mapping.get(header)
                if field_name and field_name != 'centre_code':  # Avoid reprocessing centre_code
                    if field_name == 'department_code':
                        try:
                            department = Department.objects.get(code=value) if value else None
                            setattr(import_instance, 'department', department)
                            print(f"Setting department to {department.name if department else None} (code: {value})")
                        except Department.DoesNotExist:
                            print(f"Department with code {value} not found, setting to None")
                            setattr(import_instance, 'department', None)
                    elif field_name == 'date' and value:
                        try:
                            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
                                try:
                                    date_value = datetime.strptime(value, fmt).date()
                                    setattr(import_instance, field_name, date_value)
                                    break
                                except ValueError:
                                    continue
                            else:
                                print(f"Invalid date format: {value}")
                                setattr(import_instance, field_name, None)
                        except Exception as e:
                            print(f"Error parsing date {value}: {e}")
                            setattr(import_instance, field_name, None)
                    else:
                        setattr(import_instance, field_name, value or None)
                        print(f"Setting {field_name} to {value or None}")
            import_instances.append(import_instance)

        if import_instances:
            print(f"Creating {len(import_instances)} instances")
            with transaction.atomic():
                Import.objects.bulk_create(import_instances)
        else:
            print("No valid instances to create")

    except ValueError as ve:
        print(f"Validation error: {ve}")
        raise
    except Exception as e:
        print(f"Error processing CSV file: {str(e)}")
        raise
    finally:
        decoded_file.detach()

@login_required
def upload_csv(request):
    if request.method == 'POST':
        if 'file' in request.FILES:
            try:
                upload_dir = os.path.join(settings.MEDIA_ROOT, 'Uploads')
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, request.FILES['file'].name)
                with open(file_path, 'wb') as destination:
                    for chunk in request.FILES['file'].chunks():
                        destination.write(chunk)
                request.FILES['file'].seek(0)
                handle_uploaded_file(request.FILES['file'], request.user)
                messages.success(request, "CSV file uploaded and data imported successfully.")
                return redirect('display_approved_imports')
            except Exception as e:
                messages.error(request, f"Error processing CSV file: {str(e)}")
        else:
            try:
                with transaction.atomic():
                    centre = request.POST.get('centre')
                    if centre:
                        centre_obj = Centre.objects.get(id=centre) if centre != 'None' else None
                    else:
                        centre_obj = None
                    user = CustomUser.objects.create_user(
                        username=request.POST.get('username'),
                        email=request.POST.get('email'),
                        password=request.POST.get('password'),
                        first_name=request.POST.get('first_name', ''),
                        last_name=request.POST.get('last_name', ''),
                        centre=centre_obj,
                        is_trainer=request.POST.get('is_trainer') == 'on',
                        is_staff=request.POST.get('is_staff') == 'on',
                        is_superuser=request.POST.get('is_superuser') == 'on'
                    )
                    user.save()
                    messages.success(request, "Record saved successfully.")
                    return redirect('display_approved_imports')
            except Exception as e:
                messages.error(request, f"Error saving record: {str(e)}")
    else:
        return render(request, 'import/uploadcsv.html', {'centres': Centre.objects.all()})

@login_required
def import_add(request):
    if request.method == 'POST':
        if 'file' in request.FILES:
            # Check if file is CSV
            file = request.FILES['file']
            if not file.name.lower().endswith('.csv'):
                messages.error(request, "Only CSV files are accepted for upload. Please convert your file to CSV format.")
                return redirect('import_add')
            # Handle bulk CSV upload
            try:
                handle_uploaded_file(file, request.user)
                messages.success(request, "CSV file uploaded and data imported successfully.")
                return redirect('display_approved_imports')
            except ValueError as ve:
                messages.error(request, str(ve))
                return redirect('import_add')
            except Exception as e:
                messages.error(request, f"Error processing CSV file: {str(e)}")
                return redirect('import_add')
        else:
            # Handle single device form submission
            try:
                with transaction.atomic():
                    centre_id = request.POST.get('centre')
                    centre = Centre.objects.get(id=centre_id) if centre_id and centre_id != '' else None
                    if request.user.is_trainer and centre != request.user.centre:
                        messages.error(request, "You are only allowed to add records for your own centre.")
                        return redirect('import_add')
                    # Validate required fields
                    required_fields = {
                        'department': request.POST.get('department'),
                        'hardware': request.POST.get('hardware'),
                        'system_model': request.POST.get('system_model'),
                        'serial_number': request.POST.get('serial_number'),
                        'assignee_first_name': request.POST.get('assignee_first_name'),
                        'assignee_last_name': request.POST.get('assignee_last_name'),
                        'device_condition': request.POST.get('device_condition'),
                        'status': request.POST.get('status')
                    }
                    for field_name, value in required_fields.items():
                        if not value:
                            messages.error(request, f"{field_name.replace('_', ' ').title()} is required.")
                            return redirect('import_add')
                    department_id = request.POST.get('department')
                    department = Department.objects.get(id=department_id) if department_id and department_id != 'None' else None
                    if not department:
                        messages.error(request, "Department is required.")
                        return redirect('import_add')
                    import_instance = Import(
                        added_by=request.user,
                        centre=centre,
                        department=department,
                        hardware=request.POST.get('hardware'),
                        system_model=request.POST.get('system_model'),
                        processor=request.POST.get('processor'),
                        ram_gb=request.POST.get('ram_gb'),
                        hdd_gb=request.POST.get('hdd_gb'),
                        serial_number=request.POST.get('serial_number'),
                        assignee_first_name=request.POST.get('assignee_first_name'),
                        assignee_last_name=request.POST.get('assignee_last_name'),
                        assignee_email_address=request.POST.get('assignee_email_address'),
                        device_condition=request.POST.get('device_condition'),
                        status=request.POST.get('status'),
                        date=timezone.now().date(),  # Set to current date
                        is_approved=False if request.user.is_trainer else True,
                        approved_by=request.user if request.user.is_superuser else None
                    )
                    if import_instance.serial_number and Import.objects.filter(serial_number=import_instance.serial_number).exists():
                        messages.error(request, f"Serial number {import_instance.serial_number} already exists.")
                        return redirect('import_add')
                    import_instance.save()
                    messages.success(request, "Record added successfully.")
                    return redirect('display_approved_imports')
            except Centre.DoesNotExist:
                messages.error(request, "Invalid centre selected.")
                return redirect('import_add')
            except Department.DoesNotExist:
                messages.error(request, "Invalid department selected.")
                return redirect('import_add')
            except Exception as e:
                messages.error(request, f"Error adding record: {str(e)}")
                return redirect('import_add')
    return render(request, 'import/add.html', {'centres': Centre.objects.all(), 'departments': Department.objects.all()})

@login_required
def import_update(request, pk):
    import_instance = get_object_or_404(Import, pk=pk)
    if request.user.is_trainer and import_instance.centre != request.user.centre:
        messages.error(request, "Trainers can only update records for their own centre.")
        return redirect('display_csv')
    if request.method == 'POST':
        try:
            with transaction.atomic():
                centre_id = request.POST.get('centre')
                centre = Centre.objects.get(id=centre_id) if centre_id and centre_id != 'None' else None
                if request.user.is_trainer and centre != request.user.centre:
                    messages.error(request, "Trainers can only update records for their own centre.")
                    return redirect('display_csv')
                if request.user.is_trainer and not request.POST.get('reason_for_update'):
                    messages.error(request, "Reason for update is required for trainers.")
                    return redirect('display_csv')
                serial_number = request.POST.get('serial_number', '')
                if serial_number and Import.objects.filter(serial_number=serial_number).exclude(id=pk).exists():
                    messages.error(request, f"Serial number {serial_number} already exists.")
                    return redirect('display_csv')
                department_id = request.POST.get('department')
                department = Department.objects.get(id=department_id) if department_id and department_id != 'None' else None
                if request.user.is_trainer:
                    # Store pending update
                    pending_update = PendingUpdate.objects.create(
                        import_record=import_instance,
                        centre=centre,
                        department=department,
                        hardware=request.POST.get('hardware', ''),
                        system_model=request.POST.get('system_model', ''),
                        processor=request.POST.get('processor', ''),
                        ram_gb=request.POST.get('ram_gb', ''),
                        hdd_gb=request.POST.get('hdd_gb', ''),
                        serial_number=serial_number,
                        assignee_first_name=request.POST.get('assignee_first_name', ''),
                        assignee_last_name=request.POST.get('assignee_last_name', ''),
                        assignee_email_address=request.POST.get('assignee_email_address', ''),
                        device_condition=request.POST.get('device_condition', ''),
                        status=request.POST.get('status', ''),
                        date=datetime.strptime(request.POST.get('date'), '%Y-%m-%d').date() if request.POST.get('date') else None,
                        reason_for_update=request.POST.get('reason_for_update', ''),
                        updated_by=request.user
                    )
                    import_instance.is_approved = False
                    import_instance.approved_by = None
                    import_instance.save()
                    messages.success(request, "Update submitted for approval. Check your notifications for updates.")
                    return redirect('notifications_view')  # Redirect to notifications page
                else:
                    # Apply update directly for superusers
                    import_instance.centre = centre
                    import_instance.department = department
                    import_instance.hardware = request.POST.get('hardware', '')
                    import_instance.system_model = request.POST.get('system_model', '')
                    import_instance.processor = request.POST.get('processor', '')
                    import_instance.ram_gb = request.POST.get('ram_gb', '')
                    import_instance.hdd_gb = request.POST.get('hdd_gb', '')
                    import_instance.serial_number = serial_number
                    import_instance.assignee_first_name = request.POST.get('assignee_first_name', '')
                    import_instance.assignee_last_name = request.POST.get('assignee_last_name', '')
                    import_instance.assignee_email_address = request.POST.get('assignee_email_address', '')
                    import_instance.device_condition = request.POST.get('device_condition', '')
                    import_instance.status = request.POST.get('status', '')
                    date_str = request.POST.get('date', '')
                    if date_str:
                        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
                            try:
                                import_instance.date = datetime.strptime(date_str, fmt).date()
                                break
                            except ValueError:
                                continue
                    if request.user.is_superuser and request.POST.get('is_approved') == 'on':
                        import_instance.is_approved = True
                        import_instance.approved_by = request.user
                    import_instance.save()
                    messages.success(request, "Record updated successfully.")
                    return redirect('display_csv')
        except Department.DoesNotExist:
            messages.error(request, "Invalid department selected.")
            return redirect('display_csv')
        except Exception as e:
            logger.error(f"Error updating record: {str(e)}")
            messages.error(request, f"Error updating record: {str(e)}")
            return redirect('display_csv')
    return redirect('display_csv')

@login_required
@user_passes_test(lambda u: u.is_superuser and not u.is_trainer)
def import_approve(request, pk):
    import_instance = get_object_or_404(Import, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            pending_update = PendingUpdate.objects.filter(import_record=import_instance).order_by('-created_at').first()
            if pending_update:
                # Apply pending update
                import_instance.centre = pending_update.centre
                import_instance.department = pending_update.department
                import_instance.hardware = pending_update.hardware
                import_instance.system_model = pending_update.system_model
                import_instance.processor = pending_update.processor
                import_instance.ram_gb = pending_update.ram_gb
                import_instance.hdd_gb = pending_update.hdd_gb
                import_instance.serial_number = pending_update.serial_number
                import_instance.assignee_first_name = pending_update.assignee_first_name
                import_instance.assignee_last_name = pending_update.assignee_last_name
                import_instance.assignee_email_address = pending_update.assignee_email_address
                import_instance.device_condition = pending_update.device_condition
                import_instance.status = pending_update.status
                import_instance.date = pending_update.date
                import_instance.reason_for_update = pending_update.reason_for_update
                import_instance.is_approved = True
                import_instance.approved_by = request.user
                import_instance.save()
                pending_update.delete()
                messages.success(request, "Record approved and updated successfully.")
            else:
                # Approve without pending update
                import_instance.is_approved = True
                import_instance.approved_by = request.user
                import_instance.save()
                messages.success(request, "Record approved successfully.")
            return redirect('display_csv')
    return redirect('display_csv')

@login_required
@user_passes_test(lambda u: u.is_superuser and not u.is_trainer)
def import_approve_all(request):
    if request.method == 'POST':
        # Get pagination and search parameters
        page_number = request.GET.get('page', '1')
        items_per_page = request.GET.get('items_per_page', '10')
        search_query = request.GET.get('search', '')
        
        try:
            items_per_page = int(items_per_page)
            if items_per_page not in [10, 25, 50, 100, 500]:
                items_per_page = 10
        except ValueError:
            items_per_page = 10

        try:
            page_number = int(page_number) if page_number else 1  # Default to page 1 if empty
        except ValueError:
            page_number = 1

        # Filter data based on user permissions and search query
        data = Import.objects.filter(is_approved=False) if request.user.is_superuser else Import.objects.none()
        if search_query:
            query = (
                Q(centre__name__icontains=search_query) |
                Q(centre__centre_code__icontains=search_query) |
                Q(department__code__icontains=search_query) |
                Q(hardware__icontains=search_query) |
                Q(system_model__icontains=search_query) |
                Q(processor__icontains=search_query) |
                Q(ram_gb__icontains=search_query) |
                Q(hdd_gb__icontains=search_query) |
                Q(serial_number__icontains=search_query) |
                Q(assignee_first_name__icontains=search_query) |
                Q(assignee_last_name__icontains=search_query) |
                Q(assignee_email_address__icontains=search_query) |
                Q(device_condition__icontains=search_query) |
                Q(status__icontains=search_query) |
                Q(date__icontains=search_query) |
                Q(reason_for_update__icontains=search_query)
            )
            data = data.filter(query)

        # Paginate data
        paginator = Paginator(data, items_per_page)
        try:
            data_on_page = paginator.page(page_number)
        except PageNotAnInteger:
            data_on_page = paginator.page(1)
        except EmptyPage:
            data_on_page = paginator.page(paginator.num_pages)

        # Approve records with pending updates or is_approved=False
        approved_count = 0
        with transaction.atomic():
            for item in data_on_page:
                pending_update = PendingUpdate.objects.filter(import_record=item).order_by('-created_at').first()
                if pending_update:
                    # Apply pending update
                    item.centre = pending_update.centre
                    item.department = pending_update.department
                    item.hardware = pending_update.hardware
                    item.system_model = pending_update.system_model
                    item.processor = pending_update.processor
                    item.ram_gb = pending_update.ram_gb
                    item.hdd_gb = pending_update.hdd_gb
                    item.serial_number = pending_update.serial_number
                    item.assignee_first_name = pending_update.assignee_first_name
                    item.assignee_last_name = pending_update.assignee_last_name
                    item.assignee_email_address = pending_update.assignee_email_address
                    item.device_condition = pending_update.device_condition
                    item.status = pending_update.status
                    item.date = pending_update.date
                    item.reason_for_update = pending_update.reason_for_update
                    item.is_approved = True
                    item.approved_by = request.user
                    item.save()
                    pending_update.delete()
                    approved_count += 1
                    # Mark related notifications as read
                    content_type = ContentType.objects.get_for_model(Import)
                    Notification.objects.filter(
                        content_type=content_type,
                        object_id=item.pk,
                        is_read=False
                    ).update(is_read=True)
                elif not item.is_approved:
                    # Approve records without pending updates
                    item.is_approved = True
                    item.approved_by = request.user
                    item.save()
                    approved_count += 1
                    # Mark related notifications as read
                    content_type = ContentType.objects.get_for_model(Import)
                    Notification.objects.filter(
                        content_type=content_type,
                        object_id=item.pk,
                        is_read=False
                    ).update(is_read=True)

        if approved_count > 0:
            messages.success(request, f"{approved_count} record(s) approved successfully.")
        else:
            messages.info(request, "No unapproved records to approve on this page.")
        
        # Construct redirect URL with query parameters
        redirect_url = reverse('display_csv')  # Resolve the display_csv URL
        query_params = []
        query_params.append(f"page={page_number}")
        query_params.append(f"items_per_page={items_per_page}")
        if search_query:
            query_params.append(f"search={search_query}")
        redirect_url += "?" + "&".join(query_params)
        return redirect(redirect_url)
    return redirect('display_csv')

@login_required
@user_passes_test(lambda u: not u.is_trainer)
def import_delete(request, pk):
    import_instance = get_object_or_404(Import, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            import_instance.delete()
            messages.success(request, "Record deleted successfully.")
        return redirect('display_csv')
    return redirect('display_csv')

@login_required
def imports_add(request):
    return upload_csv(request)

@login_required
def imports_view(request):
    return display_approved_imports(request)

@login_required
def export_to_excel(request):
    scope = request.GET.get('scope', 'page')
    search_query = request.GET.get('search', '')
    page_number = request.GET.get('page', '1')
    items_per_page = request.GET.get('items_per_page', '10')

    try:
        items_per_page = int(items_per_page)
        if items_per_page not in [10, 25, 50, 100, 500]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    try:
        page_number = int(page_number) if page_number else 1
    except ValueError:
        page_number = 1

    if request.user.is_superuser:
        data = Import.objects.all()
    elif request.user.is_trainer:
        data = Import.objects.filter(centre=request.user.centre)
    else:
        data = Import.objects.none()

    if search_query:
        query = (
            Q(centre__name__icontains=search_query) |
            Q(centre__centre_code__icontains=search_query) |
            Q(department__code__icontains=search_query) |
            Q(hardware__icontains=search_query) |
            Q(system_model__icontains=search_query) |
            Q(processor__icontains=search_query) |
            Q(ram_gb__icontains=search_query) |
            Q(hdd_gb__icontains=search_query) |
            Q(serial_number__icontains=search_query) |
            Q(assignee_first_name__icontains=search_query) |
            Q(assignee_last_name__icontains=search_query) |
            Q(assignee_email_address__icontains=search_query) |
            Q(device_condition__icontains=search_query) |
            Q(status__icontains=search_query) |
            Q(date__icontains=search_query) |
            Q(reason_for_update__icontains=search_query)
        )
        data = data.filter(query)

    if scope == 'page':
        paginator = Paginator(data, items_per_page)
        try:
            data = paginator.page(page_number)
        except (PageNotAnInteger, EmptyPage):
            data = paginator.page(1)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IT Inventory"

    headers = [
        'Centre_code', 'Department Code', 'Hardware', 'System Model', 'Processor', 'RAM (GB)', 'HDD (GB)',
        'Serial Number', 'Assignee First Name', 'Assignee Last Name', 'Assignee Email',
        'Device Condition', 'Status', 'Date', 'Added By', 'Approved By', 'Is Approved'
    ]
    ws.append(headers)

    for item in data:
        ws.append([
            item.centre.centre_code if item.centre else 'N/A',
            item.department.department_code if item.department else 'N/A',
            item.hardware or 'N/A',
            item.system_model or 'N/A',
            item.processor or 'N/A',
            item.ram_gb or 'N/A',
            item.hdd_gb or 'N/A',
            item.serial_number or 'N/A',
            item.assignee_first_name or 'N/A',
            item.assignee_last_name or 'N/A',
            item.assignee_email_address or 'N/A',
            item.device_condition or 'N/A',
            item.status or 'N/A',
            item.date.strftime('%Y-%m-%d') if item.date else '',
            item.added_by.username if item.added_by else '',
            item.approved_by.username if item.approved_by else '',
            'Yes' if item.is_approved else 'No'
            
        ])

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    filename = 'IT_Inventory_All.xlsx' if scope == 'all' else 'IT_Inventory_Page.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response

@login_required
def export_to_pdf(request):
    scope = request.GET.get('scope', 'page')
    search_query = request.GET.get('search', '')
    page_number = request.GET.get('page', '1')
    items_per_page = request.GET.get('items_per_page', '10')

    logger.debug(f"Scope: {scope}, Search: {search_query}, Page: {page_number}, Items per page: {items_per_page}")

    try:
        items_per_page = int(items_per_page)
        if items_per_page not in [10, 25, 50, 100, 500]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    try:
        page_number = int(page_number) if page_number else 1
    except ValueError:
        page_number = 1

    # Filter data with minimal fields to reduce memory usage
    if request.user.is_superuser and not request.user.is_trainer:
        data = Import.objects.only(
            'centre__name', 'department__name', 'hardware', 'system_model', 'processor',
            'ram_gb', 'hdd_gb', 'serial_number', 'assignee_first_name',
            'assignee_last_name', 'assignee_email_address', 'device_condition',
            'status', 'date', 'reason_for_update'
        )
    elif request.user.is_trainer:
        data = Import.objects.filter(centre=request.user.centre).only(
            'centre__name', 'department__name', 'hardware', 'system_model', 'processor',
            'ram_gb', 'hdd_gb', 'serial_number', 'assignee_first_name',
            'assignee_last_name', 'assignee_email_address', 'device_condition',
            'status', 'date', 'reason_for_update'
        )
    else:
        data = Import.objects.none()

    # Apply search query
    if search_query:
        query = (
            Q(centre__name__icontains=search_query) |
            Q(centre__centre_name__icontains=search_query) |
            Q(department__name__icontains=search_query) |
            Q(hardware__icontains=search_query) |
            Q(system_model__icontains=search_query) |
            Q(processor__icontains=search_query) |
            Q(ram_gb__icontains=search_query) |
            Q(hdd_gb__icontains=search_query) |
            Q(serial_number__icontains=search_query) |
            Q(assignee_first_name__icontains=search_query) |
            Q(assignee_last_name__icontains=search_query) |
            Q(assignee_email_address__icontains=search_query) |
            Q(device_condition__icontains=search_query) |
            Q(status__icontains=search_query) |
            Q(date__icontains=search_query) |
            Q(reason_for_update__icontains=search_query)
        )
        data = data.filter(query)

    # Log the number of records
    record_count = data.count()
    logger.debug(f"Queryset record count: {record_count}")

    # Apply pagination for scope='page'
    if scope == 'page':
        paginator = Paginator(data, items_per_page)
        try:
            data = paginator.page(page_number)
        except (PageNotAnInteger, EmptyPage):
            data = paginator.page(1)
        logger.debug(f"Paginated data count: {len(data)}")
    else:
        data = data.iterator()  # Memory-efficient for large datasets

    # Initialize PDF response
    response = HttpResponse(content_type='application/pdf')
    filename = 'IT_Inventory_All.pdf' if scope == 'all' else 'IT_Inventory_Page.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # Set up ReportLab document in landscape mode
    doc = SimpleDocTemplate(
        response,
        pagesize=(A4[1], A4[0]),  # Landscape: 842pt width x 595pt height
        rightMargin=10*mm,
        leftMargin=10*mm,
        topMargin=15*mm,
        bottomMargin=15*mm
    )
    elements = []

    # Register font (optional: use DejaVuSans for Unicode support)
    font_name = 'Helvetica'  # Default font for simplicity

    # Styles
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    subtitle_style = ParagraphStyle(name='Subtitle', parent=styles['Normal'], fontSize=10, spaceAfter=10)
    cell_style = ParagraphStyle(name='Cell', fontName=font_name, fontSize=7, leading=8, alignment=TA_LEFT, wordWrap='CJK')

    # Add title and subtitle
    if request.user.is_superuser:
        elements.append(Paragraph('MOHO IT Inventory Report', title_style))
    elif request.user.is_trainer:
        elements.append(Paragraph(f'{request.user.centre} IT Inventory Report', title_style))
        
    elements.append(Paragraph(f'Generated on {datetime.now().strftime("%Y-%m-%d")}', subtitle_style))
    elements.append(Spacer(1, 6*mm))

    # Table headers (aligned with HTML template)
    headers = ['Device Details', 'Centre', 'Assignee Info', 'Status & Date']
    col_widths = [250, 150, 200, 200]  # Total: 800pt, fits within 842pt - 56pt margins

    # Prepare table data
    table_data = [headers]
    row_count = 0

    def safe_str(value):
        return str(value or 'N/A').encode('utf-8', errors='replace').decode('utf-8')

    for item in data:
        row_count += 1
        logger.debug(f"Processing item {row_count}: Serial No. {safe_str(item.serial_number)}")
        # Group data as per HTML template, using <br/> for line breaks
        device_details = (
            f"<b>Serial:</b> {safe_str(item.serial_number)}<br/>"
            f"<b>Hardware:</b> {safe_str(item.hardware)}<br/>"
            f"<b>Model:</b> {safe_str(item.system_model)}<br/>"
            f"<b>Processor:</b> {safe_str(item.processor)}<br/>"
            f"<b>RAM:</b> {safe_str(item.ram_gb)} GB<br/>"
            f"<b>HDD:</b> {safe_str(item.hdd_gb)} GB"
        )
        centre_info = (
            f"<b>Centre:</b> {safe_str(item.centre.name if item.centre else 'N/A')}<br/>"
            f"<b>Dept:</b> {safe_str(item.department.department_code if item.department else 'N/A')}"
        )
        assignee_info = (
            f"<b>Name:</b> {safe_str(item.assignee_first_name)} {safe_str(item.assignee_last_name)}<br/>"
            f"<b>Email:</b> {safe_str(item.assignee_email_address)}"
        )
        status_date = (
            f"<b>Status:</b> {safe_str(item.status)}<br/>"
            f"<b>Condition:</b> {safe_str(item.device_condition)}<br/>"
            f"<b>Date:</b> {safe_str(item.date.strftime('%Y-%m-%d') if item.date else 'N/A')}<br/>"
            f"<b>Reason:</b> {safe_str(item.reason_for_update)}"
        )
        row = [
            Paragraph(device_details, cell_style),
            Paragraph(centre_info, cell_style),
            Paragraph(assignee_info, cell_style),
            Paragraph(status_date, cell_style)
        ]
        table_data.append(row)

    # If no data, add a placeholder row
    if row_count == 0:
        table_data.append([Paragraph('No records found.', cell_style)] * 4)
        logger.debug("No records were added to the PDF.")

    # Create table
    table = Table(table_data, colWidths=col_widths, rowHeights=None)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), font_name),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    elements.append(table)

    # Build PDF
    try:
        doc.build(elements)
        logger.debug("PDF generated successfully.")
    except Exception as e:
        logger.error(f"PDF generation failed: {str(e)}")
        return HttpResponse(f"Error generating PDF: {str(e)}", status=500)

    # Clean up memory
    gc.collect()
    return response

@login_required
def profile(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        # Do not update centre, is_trainer, is_staff, or is_superuser from POST data
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
            user.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('profile')

    centres = Centre.objects.all()
    return render(request, 'accounts/profile.html', {
        'user': request.user,
        'centres': centres,
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

@login_required
def device_history(request, pk):
    device = get_object_or_404(Import, pk=pk)
    history = device.history.all().order_by('-history_date')
    history_data = []
    for record in history:
        diff = {}
        if record.prev_record:
            changes = record.diff_against(record.prev_record)
            if changes:
                for change in changes.changes:
                    if hasattr(change, 'field') and hasattr(change, 'old') and hasattr(change, 'new'):
                        diff[change.field] = {'old': change.old, 'new': change.new}
        history_data.append({
            'record': record,
            'diff': diff,
            'change_type': record.get_history_type_display() or record.history_type,
            'user': record.history_user.username if record.history_user else 'System'
        })
    context = {'device': device, 'history': history_data}
    return render(request, 'import/device_history.html', context)

@login_required
def display_approved_imports(request):
    if request.user.is_superuser:
        data = Import.objects.filter(is_approved=True)
    elif request.user.is_trainer:
        if not request.user.centre:
            data = Import.objects.none()
        else:
            data = Import.objects.filter(centre=request.user.centre, is_approved=True)
    else:
        data = Import.objects.none()

    search_query = request.GET.get('search', '').strip()
    if search_query:
        query = Q()
        for field in [
            'centre__name', 'centre__centre_code', 'department__code', 'hardware',
            'system_model', 'processor', 'ram_gb', 'hdd_gb', 'serial_number',
            'assignee_first_name', 'assignee_last_name', 'assignee_email_address',
            'device_condition', 'status', 'reason_for_update'
        ]:
            query |= Q(**{f'{field}__icontains': search_query}) & ~Q(**{f'{field}__isnull': True}) & ~Q(**{f'{field}': ''})
            if field not in ['date']:
                query |= Q(**{f'{field}__isnull': True}) & Q(**{f'{field}__iregex': r'^(?:{})$'.format(re.escape(search_query))})
        data = data.filter(query)

    # Force queryset evaluation to ensure data is available
    data = list(data)  # Convert to list to materialize the queryset
    items_per_page = request.GET.get('items_per_page', '10')
    try:
        items_per_page = int(items_per_page)
        if items_per_page not in [10, 25, 50, 100, 500]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    paginator = Paginator(data, items_per_page)
    page_number = request.GET.get('page', 1)
    try:
        data_on_page = paginator.page(page_number)
    except PageNotAnInteger:
        data_on_page = paginator.page(1)
    except EmptyPage:
        data_on_page = paginator.page(paginator.num_pages)
    except Exception as e:
        messages.error(request, f"Pagination error: {str(e)}")
        data_on_page = paginator.page(1)

    data_with_pending = []
    unapproved_count = 0  # Should be 0 for approved imports, but kept for consistency
    for item in data_on_page.object_list:  # Use object_list to access the paginated items
        pending_update = getattr(item, 'pending_updates', None).order_by('-created_at').first() if hasattr(item, 'pending_updates') else None
        data_with_pending.append({'item': item, 'pending_update': pending_update})
        if not getattr(item, 'is_approved', True):  # Should always be True for this view
            unapproved_count += 1

    report_data = {'total_records': paginator.count, 'search_query': search_query, 'items_per_page': items_per_page}
    items_per_page_options = [10, 25, 50, 100, 500]
    total_devices = Import.objects.count() if request.user.is_superuser else (Import.objects.filter(centre=request.user.centre).count() if request.user.is_trainer and request.user.centre else 0)
    approved_imports = total_devices - unapproved_count if total_devices is not None and unapproved_count is not None else 0

    return render(request, 'import/displaycsv_approved.html', {
        'data_with_pending': data_with_pending, 'paginator': paginator, 'data': data_on_page,
        'report_data': report_data, 'centres': Centre.objects.all(),'departments': Department.objects.all(), 'items_per_page_options': items_per_page_options,
        'unapproved_count': unapproved_count, 'total_devices': total_devices, 'approved_imports': approved_imports,
        'view_name': 'display_approved_imports'  # Added for pagination URL consistency
    })

@login_required
def display_unapproved_imports(request):
    if request.user.is_superuser:
        data = Import.objects.filter(is_approved=False)
    elif request.user.is_trainer:
        if not request.user.centre:
            data = Import.objects.none()
        else:
            data = Import.objects.filter(centre=request.user.centre, is_approved=False)
    else:
        data = Import.objects.none()

    search_query = request.GET.get('search', '').strip()
    if search_query:
        query = Q()
        for field in [
            'centre__name', 'centre__centre_code', 'department__code', 'hardware',
            'system_model', 'processor', 'ram_gb', 'hdd_gb', 'serial_number',
            'assignee_first_name', 'assignee_last_name', 'assignee_email_address',
            'device_condition', 'status', 'reason_for_update'
        ]:
            query |= Q(**{f'{field}__icontains': search_query}) & ~Q(**{f'{field}__isnull': True}) & ~Q(**{f'{field}': ''})
            if field not in ['date']:
                query |= Q(**{f'{field}__isnull': True}) & Q(**{f'{field}__iregex': r'^(?:{})$'.format(re.escape(search_query))})
        data = data.filter(query)

    # Force queryset evaluation
    data = list(data)
    items_per_page = request.GET.get('items_per_page', '10')
    try:
        items_per_page = int(items_per_page)
        if items_per_page not in [10, 25, 50, 100, 500]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    paginator = Paginator(data, items_per_page)
    page_number = request.GET.get('page', 1)
    try:
        data_on_page = paginator.page(page_number)
    except PageNotAnInteger:
        data_on_page = paginator.page(1)
    except EmptyPage:
        data_on_page = paginator.page(paginator.num_pages)
    except Exception as e:
        messages.error(request, f"Pagination error: {str(e)}")
        data_on_page = paginator.page(1)

    data_with_pending = []
    unapproved_count = len(data)  # Use len() instead of count() for list
    for item in data_on_page.object_list:
        pending_update = getattr(item, 'pending_updates', None).order_by('-created_at').first() if hasattr(item, 'pending_updates') else None
        data_with_pending.append({'item': item, 'pending_update': pending_update})

    report_data = {'total_records': paginator.count, 'search_query': search_query, 'items_per_page': items_per_page}
    items_per_page_options = [10, 25, 50, 100, 500]
    total_devices = Import.objects.count() if request.user.is_superuser else (Import.objects.filter(centre=request.user.centre).count() if request.user.is_trainer and request.user.centre else 0)
    approved_imports = total_devices - unapproved_count if total_devices is not None and unapproved_count is not None else 0

    return render(request, 'import/displaycsv_unapproved.html', {
        'data_with_pending': data_with_pending, 'paginator': paginator, 'data': data_on_page,
        'report_data': report_data, 'centres': Centre.objects.all(), 'departments': Department.objects.all(), 'items_per_page_options': items_per_page_options,
        'unapproved_count': unapproved_count, 'total_devices': total_devices, 'approved_imports': approved_imports,
        'view_name': 'display_unapproved_imports'
    })

@login_required
def dashboard_view(request):
    if request.user.is_superuser and not request.user.is_trainer:
        total_devices = Import.objects.count()
        pending_approvals = Import.objects.filter(is_approved=False).count()
        total_users = CustomUser.objects.count()
        total_centres = Centre.objects.count()
        approved_imports = total_devices - pending_approvals if total_devices is not None and pending_approvals is not None else 0
        recent_devices = Import.objects.order_by('-date')[:5]
    elif request.user.is_trainer:
        if not request.user.centre:
            total_devices = 0
            pending_updates = 0
            approved_imports = 0
            recent_devices = []
        else:
            total_devices = Import.objects.filter(centre=request.user.centre).count()
            pending_updates = PendingUpdate.objects.filter(import_record__centre=request.user.centre).count()
            approved_imports = total_devices - Import.objects.filter(centre=request.user.centre, is_approved=False).count() if total_devices is not None else 0
            recent_devices = Import.objects.filter(centre=request.user.centre).order_by('-date')[:5]
    else:
        total_devices = 0
        pending_approvals = 0
        pending_updates = 0
        approved_imports = 0
        recent_devices = []

    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:5]  # Limit to 5 for card
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()

    context = {
        'total_devices': total_devices,
        'approved_imports': approved_imports,
        'pending_approvals': pending_approvals if request.user.is_superuser and not request.user.is_trainer else 0,
        'total_users': total_users if request.user.is_superuser and not request.user.is_trainer else 0,
        'total_centres': total_centres if request.user.is_superuser and not request.user.is_trainer else 0,
        'pending_updates': pending_updates if request.user.is_trainer else 0,
        'recent_devices': recent_devices,
        'notifications': notifications,
        'unread_count': unread_count,
    }

    return render(request, 'index.html', context)

@login_required
def notifications_view(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    for notification in notifications:
        print(f"Notification ID: {notification.pk}, Content Type: {notification.content_type}, Object ID: {notification.object_id}, Related Object: {notification.related_object}")
    return render(request, 'notifications.html', {'notifications': notifications})

@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if request.method == 'POST':
        notification.is_read = True
        notification.save()
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/dashboard/'))
    return HttpResponseRedirect('/dashboard/')

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        logger.debug(f"Login attempt for username: {username}")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            logger.info(f"Successful login for user: {username}")
            return redirect('dashboard')
        else:
            logger.warning(f"Failed login attempt for username: {username}")
            messages.error(request, 'Invalid username or password.')
    return render(request, 'login.html')

@login_required
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
    
    # Compute stats for each user
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

@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_delete(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if request.method == 'POST':
        if user == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect('manage_users')
        with transaction.atomic():
            user.delete()
            messages.success(request, "User deleted successfully.")
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
    groups = Group.objects.all()
    return render(request, 'manage_users.html', {'groups': groups})

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

@login_required
def clear_user(request, device_id):
    device = get_object_or_404(Import, id=device_id)
    if request.method == 'POST':
        form = ClearanceForm(request.POST)
        if form.is_valid():
            clearance = form.save(commit=False)
            clearance.device = device
            clearance.cleared_by = request.user
            clearance.save(user=request.user)  # Pass the user for history tracking
            messages.success(request, f"Device {device.serial_number} cleared successfully.")
            return redirect('display_approved_imports')
    else:
        form = ClearanceForm()
    return render(request, 'import/clear_user.html', {'form': form, 'device': device})

@login_required
def download_clearance_form(request, device_id):
    device = get_object_or_404(Import, id=device_id)
    clearance = device.clearances.order_by('-created_at').first()
    if not clearance:
        messages.error(request, "No clearance record found for this device.")
        return redirect('display_approved_imports')
    
    return render(request, 'import/clearance_form_pdf.html', {
        'device': device,
        'clearance': clearance,
        'centre': device.centre,
        'cleared_by': clearance.cleared_by,
    })