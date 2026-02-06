from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.urls import reverse
from ..models import Employee, Centre, Department, Import, CustomUser

@login_required
def employee_list(request):
    search_query = request.GET.get('search', '')
    centre_filter = request.GET.get('centre')
    department_filter = request.GET.get('department')
    items_per_page = int(request.GET.get('items_per_page', 25))

    queryset = Employee.objects.annotate(num_devices=Count('assigned_devices'))

    # Trainer restriction: only show employees in their centre
    if request.user.is_trainer and request.user.centre:
        queryset = queryset.filter(centre=request.user.centre)

    if search_query:
        queryset = queryset.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(staff_number__icontains=search_query)
        )

    if centre_filter:
        queryset = queryset.filter(centre_id=centre_filter)

    if department_filter:
        queryset = queryset.filter(department_id=department_filter)

    queryset = queryset.order_by('last_name', 'first_name')

    paginator = Paginator(queryset, items_per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

    centres = Centre.objects.all()
    if request.user.is_trainer and request.user.centre:
        centres = centres.filter(id=request.user.centre.id)

    departments = Department.objects.all()

    # Context flag for per-employee edit permission
    context = {
        'page_obj': page_obj,
        'centres': centres,
        'departments': departments,
        'search_query': search_query,
        'centre_filter': centre_filter,
        'department_filter': department_filter,
        'items_per_page': items_per_page,
        'items_per_page_options': [10, 25, 50, 100],
        'user': request.user,
    }

    # Add per-employee permission flag
    for emp in page_obj:
        emp.can_edit = (
            not request.user.is_trainer or
            (request.user.centre and emp.centre and emp.centre.id == request.user.centre.id)
        )
        context['can_edit_employee'] = emp.can_edit  # for template loop

    return render(request, 'employees/employee_list.html', context)


@login_required
def employee_add(request):
    if request.method == 'POST':
        # Trainer can only add to their own centre
        if request.user.is_trainer and request.user.centre:
            centre_id = request.user.centre.id
        else:
            centre_id = request.POST.get('centre') or None

        try:
            first_name = request.POST['first_name'].strip()
            last_name = request.POST['last_name'].strip()
            email = request.POST.get('email', '').strip() or None
            staff_number = request.POST.get('staff_number', '').strip() or None
            designation = request.POST.get('designation', '').strip() or None
            department_id = request.POST.get('department') or None
            is_active = 'is_active' in request.POST

            centre = Centre.objects.get(pk=centre_id) if centre_id else None
            department = Department.objects.get(pk=department_id) if department_id else None

            Employee.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                staff_number=staff_number,
                designation=designation,
                centre=centre,
                department=department,
                is_active=is_active,
            )
            messages.success(request, 'Employee added successfully.')
        except Exception as e:
            messages.error(request, f'Error adding employee: {str(e)}')

        return redirect(reverse('employee_list') + '?' + request.GET.urlencode())

    return redirect('employee_list')


@login_required
def employee_update(request, pk):
    employee = get_object_or_404(Employee, pk=pk)

    # Permission check: trainers can only edit employees in their centre
    if request.user.is_trainer and (not employee.centre or employee.centre != request.user.centre):
        messages.error(request, "You can only edit employees in your own centre.")
        return redirect('employee_list')

    if request.method == 'POST':
        try:
            employee.first_name = request.POST['first_name'].strip()
            employee.last_name = request.POST['last_name'].strip()
            employee.email = request.POST.get('email', '').strip() or None
            employee.staff_number = request.POST.get('staff_number', '').strip() or None
            employee.designation = request.POST.get('designation', '').strip() or None
            employee.department = Department.objects.get(pk=request.POST.get('department')) if request.POST.get('department') else None
            employee.is_active = 'is_active' in request.POST

            # Trainers cannot change centre
            if not request.user.is_trainer:
                centre_id = request.POST.get('centre') or None
                employee.centre = Centre.objects.get(pk=centre_id) if centre_id else None

            employee.save()
            messages.success(request, 'Employee updated successfully.')
        except Exception as e:
            messages.error(request, f'Error updating employee: {str(e)}')

        return redirect(reverse('employee_list') + '?' + request.GET.urlencode())

    return redirect('employee_list')


@login_required
def employee_delete(request, pk):
    employee = get_object_or_404(Employee, pk=pk)

    # Permission check
    if request.user.is_trainer and (not employee.centre or employee.centre != request.user.centre):
        messages.error(request, "You can only delete employees in your own centre.")
        return redirect('employee_list')

    if request.method == 'POST':
        if employee.assigned_devices.exists():
            messages.error(request, 'Cannot delete employee who is currently assigned to one or more devices.')
        else:
            employee.delete()
            messages.success(request, 'Employee deleted successfully.')

        return redirect(reverse('employee_list') + '?' + request.GET.urlencode())

    return redirect('employee_list')