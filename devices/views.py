import csv
from io import TextIOWrapper
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from datetime import datetime
from .forms import ImportForm
from .models import Import, Centre
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from reportlab.pdfgen import canvas
from django.http import HttpResponse
import openpyxl
from django.template.loader import get_template
from xhtml2pdf import pisa
from io import BytesIO
import os
from django.conf import settings

def handle_uploaded_file(file, user):
    header_mapping = {
        'centre': 'centre',
        'department': 'department',
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

        required_headers = ['centre', 'serial_number']
        missing_headers = [h for h in required_headers if h not in headers]
        if missing_headers:
            raise ValueError(f"Missing required headers: {', '.join(missing_headers)}")

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
            import_instance = Import(added_by=user)  # Set added_by to the logged-in user
            for header, value in zip(headers, row):
                value = value.strip()
                field_name = header_mapping.get(header)
                if field_name:
                    if field_name == 'centre' and value:
                        try:
                            centre = Centre.objects.get(centre_code=value)
                            import_instance.centre = centre
                            print(f"Mapped centre_code {value} to Centre: {centre.name}")
                        except Centre.DoesNotExist:
                            print(f"Centre with centre_code {value} not found, setting to None")
                            import_instance.centre = None
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

    except Exception as e:
        print(f"Error processing CSV file: {e}")
        raise
    finally:
        decoded_file.detach()

def upload_csv(request):
    if request.method == 'POST':
        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            if 'file' in request.FILES:
                try:
                    # Save the file to disk
                    upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads')
                    os.makedirs(upload_dir, exist_ok=True)
                    file_path = os.path.join(upload_dir, request.FILES['file'].name)
                    with open(file_path, 'wb') as destination:
                        for chunk in request.FILES['file'].chunks():
                            destination.write(chunk)
                    # Process CSV data
                    request.FILES['file'].seek(0)
                    handle_uploaded_file(request.FILES['file'], request.user)
                    messages.success(request, "CSV file uploaded and data imported successfully.")
                    return redirect('import_displaycsv')
                except Exception as e:
                    messages.error(request, f"Error processing CSV file: {str(e)}")
            else:
                # Handle manual record creation
                try:
                    instance = form.save(commit=False)
                    instance.added_by = request.user
                    instance.save()
                    messages.success(request, "Record saved successfully.")
                    return redirect('import_displaycsv')
                except Exception as e:
                    messages.error(request, f"Error saving record: {str(e)}")
        else:
            messages.error(request, "Form is not valid. Please check the input and try again.")
    else:
        form = ImportForm()
    return render(request, 'import/uploadcsv.html', {'form': form})

def display_csv(request):
    if request.user.is_superuser:
        data = Import.objects.all()
    elif request.user.is_trainer:
        data = Import.objects.filter(centre=Centre.objects.get(centre_code=request.user.centre.centre_code))
    # Get individual search parameters
    centre = request.GET.get('centre', '')
    department = request.GET.get('department', '')
    hardware = request.GET.get('hardware', '')
    system_model = request.GET.get('system_model', '')
    processor = request.GET.get('processor', '')
    ram_gb = request.GET.get('ram_gb', '')
    hdd_gb = request.GET.get('hdd_gb', '')
    serial_number = request.GET.get('serial_number', '')
    assignee_first_name = request.GET.get('assignee_first_name', '')
    assignee_last_name = request.GET.get('assignee_last_name', '')
    assignee_email_address = request.GET.get('assignee_email_address', '')
    device_condition = request.GET.get('device_condition', '')
    status = request.GET.get('status', '')
    date = request.GET.get('date', '')

    # Apply filters if search parameters are provided
    if any([centre, department, hardware, system_model, processor, ram_gb, hdd_gb,
            serial_number, assignee_first_name, assignee_last_name, assignee_email_address,
            device_condition, status, date]):
        query = Q()
        if centre:
            query &= Q(centre__centre_code__icontains=centre)
        if department:
            query &= Q(department__icontains=department)
        if hardware:
            query &= Q(hardware__icontains=hardware)
        if system_model:
            query &= Q(system_model__icontains=system_model)
        if processor:
            query &= Q(processor__icontains=processor)
        if ram_gb:
            query &= Q(ram_gb__icontains=ram_gb)
        if hdd_gb:
            query &= Q(hdd_gb__icontains=hdd_gb)
        if serial_number:
            query &= Q(serial_number__icontains=serial_number)
        if assignee_first_name:
            query &= Q(assignee_first_name__icontains=assignee_first_name)
        if assignee_last_name:
            query &= Q(assignee_last_name__icontains=assignee_last_name)
        if assignee_email_address:
            query &= Q(assignee_email_address__icontains=assignee_email_address)
        if device_condition:
            query &= Q(device_condition__icontains=device_condition)
        if status:
            query &= Q(status__icontains=status)
        if date:
            query &= Q(date__icontains=date)
        data = data.filter(query)

    items_per_page = 100
    paginator = Paginator(data, items_per_page)
    page_number = request.GET.get('page', 1)

    try:
        page_number = int(page_number)
    except ValueError:
        page_number = 1

    try:
        data_on_page = paginator.page(page_number)
    except PageNotAnInteger:
        data_on_page = paginator.page(1)
    except EmptyPage:
        data_on_page = paginator.page(paginator.num_pages)

    report_data = {
        'total_records': data.count(),
        'centre': centre,
        'department': department,
        'hardware': hardware,
        'system_model': system_model,
        'processor': processor,
        'ram_gb': ram_gb,
        'hdd_gb': hdd_gb,
        'serial_number': serial_number,
        'assignee_first_name': assignee_first_name,
        'assignee_last_name': assignee_last_name,
        'assignee_email_address': assignee_email_address,
        'device_condition': device_condition,
        'status': status,
        'date': date,
    }

    return render(request, 'import/displaycsv.html', {
        'data': data_on_page,
        'paginator': paginator,
        'report_data': report_data,
    })

def export_to_pdf(request):
    data = Import.objects.all()

    # Apply the same filters as in display_csv
    centre = request.GET.get('centre', '')
    department = request.GET.get('department', '')
    hardware = request.GET.get('hardware', '')
    system_model = request.GET.get('system_model', '')
    processor = request.GET.get('processor', '')
    ram_gb = request.GET.get('ram_gb', '')
    hdd_gb = request.GET.get('hdd_gb', '')
    serial_number = request.GET.get('serial_number', '')
    assignee_first_name = request.GET.get('assignee_first_name', '')
    assignee_last_name = request.GET.get('assignee_last_name', '')
    assignee_email_address = request.GET.get('assignee_email_address', '')
    device_condition = request.GET.get('device_condition', '')
    status = request.GET.get('status', '')
    date = request.GET.get('date', '')

    if any([centre, department, hardware, system_model, processor, ram_gb, hdd_gb,
            serial_number, assignee_first_name, assignee_last_name, assignee_email_address,
            device_condition, status, date]):
        query = Q()
        if centre:
            query &= Q(centre__centre_code__icontains=centre)
        if department:
            query &= Q(department__icontains=department)
        if hardware:
            query &= Q(hardware__icontains=hardware)
        if system_model:
            query &= Q(system_model__icontains=system_model)
        if processor:
            query &= Q(processor__icontains=processor)
        if ram_gb:
            query &= Q(ram_gb__icontains=ram_gb)
        if hdd_gb:
            query &= Q(hdd_gb__icontains=hdd_gb)
        if serial_number:
            query &= Q(serial_number__icontains=serial_number)
        if assignee_first_name:
            query &= Q(assignee_first_name__icontains=assignee_first_name)
        if assignee_last_name:
            query &= Q(assignee_last_name__icontains=assignee_last_name)
        if assignee_email_address:
            query &= Q(assignee_email_address__icontains=assignee_email_address)
        if device_condition:
            query &= Q(device_condition__icontains=device_condition)
        if status:
            query &= Q(status__icontains=status)
        if date:
            query &= Q(date__icontains=date)
        data = data.filter(query)

    # Apply pagination to match the current page
    items_per_page = 100
    paginator = Paginator(data, items_per_page)
    page_number = request.GET.get('page', 1)

    try:
        page_number = int(page_number)
    except ValueError:
        page_number = 1

    try:
        data_on_page = paginator.page(page_number)
    except PageNotAnInteger:
        data_on_page = paginator.page(1)
    except EmptyPage:
        data_on_page = paginator.page(paginator.num_pages)

    pdf_buffer = BytesIO()
    template_path = 'import/pdf.html'
    template = get_template(template_path)
    html = template.render({'data': data_on_page})
    pisaStatus = pisa.CreatePDF(html, dest=pdf_buffer)

    if pisaStatus.err:
        return HttpResponse('Error creating PDF', content_type='text/plain')

    pdf_buffer.seek(0)
    response = HttpResponse(pdf_buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="exported_data_page_{page_number}.pdf"'
    pdf_buffer.close()
    return response

def export_to_excel(request):
    data = Import.objects.all()

    # Apply the same filters as in display_csv
    centre = request.GET.get('centre', '')
    department = request.GET.get('department', '')
    hardware = request.GET.get('hardware', '')
    system_model = request.GET.get('system_model', '')
    processor = request.GET.get('processor', '')
    ram_gb = request.GET.get('ram_gb', '')
    hdd_gb = request.GET.get('hdd_gb', '')
    serial_number = request.GET.get('serial_number', '')
    assignee_first_name = request.GET.get('assignee_first_name', '')
    assignee_last_name = request.GET.get('assignee_last_name', '')
    assignee_email_address = request.GET.get('assignee_email_address', '')
    device_condition = request.GET.get('device_condition', '')
    status = request.GET.get('status', '')
    date = request.GET.get('date', '')

    if any([centre, department, hardware, system_model, processor, ram_gb, hdd_gb,
            serial_number, assignee_first_name, assignee_last_name, assignee_email_address,
            device_condition, status, date]):
        query = Q()
        if centre:
            query &= Q(centre__centre_code__icontains=centre)
        if department:
            query &= Q(department__icontains=department)
        if hardware:
            query &= Q(hardware__icontains=hardware)
        if system_model:
            query &= Q(system_model__icontains=system_model)
        if processor:
            query &= Q(processor__icontains=processor)
        if ram_gb:
            query &= Q(ram_gb__icontains=ram_gb)
        if hdd_gb:
            query &= Q(hdd_gb__icontains=hdd_gb)
        if serial_number:
            query &= Q(serial_number__icontains=serial_number)
        if assignee_first_name:
            query &= Q(assignee_first_name__icontains=assignee_first_name)
        if assignee_last_name:
            query &= Q(assignee_last_name__icontains=assignee_last_name)
        if assignee_email_address:
            query &= Q(assignee_email_address__icontains=assignee_email_address)
        if device_condition:
            query &= Q(device_condition__icontains=device_condition)
        if status:
            query &= Q(status__icontains=status)
        if date:
            query &= Q(date__icontains=date)
        data = data.filter(query)

    # Apply pagination to match the current page
    items_per_page = 2000
    paginator = Paginator(data, items_per_page)
    page_number = request.GET.get('page', 1)

    try:
        page_number = int(page_number)
    except ValueError:
        page_number = 1

    try:
        data_on_page = paginator.page(page_number)
    except PageNotAnInteger:
        data_on_page = paginator.page(1)
    except EmptyPage:
        data_on_page = paginator.page(paginator.num_pages)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="exported_data_page_{page_number}.xlsx"'

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = 'IT Inventory'

    headers = [
        'Centre', 'Department', 'Hardware', 'System Model', 'Processor',
        'RAM (GB)', 'HDD (GB)', 'Serial Number', 'Assignee First Name',
        'Assignee Last Name', 'Assignee Email Address', 'Device Condition',
        'Status', 'Date', 'Added By', 'Approved By', 'Is Approved', 'Reason for Update'
    ]
    for col_num, header in enumerate(headers, 1):
        worksheet.cell(row=1, column=col_num, value=header)

    for row_num, item in enumerate(data_on_page, 2):
        worksheet.cell(row=row_num, column=1, value=item.centre.centre_code if item.centre else '')
        worksheet.cell(row=row_num, column=2, value=item.department or '')
        worksheet.cell(row=row_num, column=3, value=item.hardware or '')
        worksheet.cell(row=row_num, column=4, value=item.system_model or '')
        worksheet.cell(row=row_num, column=5, value=item.processor or '')
        worksheet.cell(row=row_num, column=6, value=item.ram_gb or '')
        worksheet.cell(row=row_num, column=7, value=item.hdd_gb or '')
        worksheet.cell(row=row_num, column=8, value=item.serial_number or '')
        worksheet.cell(row=row_num, column=9, value=item.assignee_first_name or '')
        worksheet.cell(row=row_num, column=10, value=item.assignee_last_name or '')
        worksheet.cell(row=row_num, column=11, value=item.assignee_email_address or '')
        worksheet.cell(row=row_num, column=12, value=item.device_condition or '')
        worksheet.cell(row=row_num, column=13, value=item.status or '')
        worksheet.cell(row=row_num, column=14, value=str(item.date) if item.date else '')
        worksheet.cell(row=row_num, column=15, value=str(item.added_by) if item.added_by else '')
        worksheet.cell(row=row_num, column=16, value=str(item.approved_by) if item.approved_by else '')
        worksheet.cell(row=row_num, column=17, value=str(item.is_approved))
        worksheet.cell(row=row_num, column=18, value=item.reason_for_update or '')

    workbook.save(response)
    return response