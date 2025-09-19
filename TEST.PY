@login_required
@user_passes_test(lambda u: u.is_superuser and not u.is_trainer)
def import_approve(request, pk):
    import_instance = get_object_or_404(Import, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            pending_update = PendingUpdate.objects.filter(import_record=import_instance).order_by('-created_at').first()
            if pending_update:
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
                # Mark notifications as read for admins only
                content_type = ContentType.objects.get_for_model(PendingUpdate)
                Notification.objects.filter(
                    content_type=content_type,
                    object_id=pk,
                    user__is_superuser=True,
                    user__is_trainer=False,
                    is_read=False
                ).update(is_read=True, responded_by=request.user)
                messages.success(request, f"Device {import_instance.serial_number} update approved.")
            else:
                import_instance.is_approved = True
                import_instance.approved_by = request.user
                import_instance.save()
                # Mark notifications as read for admins only
                content_type = ContentType.objects.get_for_model(Import)
                Notification.objects.filter(
                    content_type=content_type,
                    object_id=import_instance.pk,
                    user__is_superuser=True,
                    user__is_trainer=False,
                    is_read=False
                ).update(is_read=True, responded_by=request.user)
                messages.success(request, f"Device {import_instance.serial_number} approved.")
            return redirect('display_unapproved_imports')
    return redirect('display_unapproved_imports')

@login_required
@user_passes_test(lambda u: u.is_superuser and not u.is_trainer)
def import_reject(request, pk):
    import_instance = get_object_or_404(Import, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            pending_update = PendingUpdate.objects.filter(import_record=import_instance).order_by('-created_at').first()
            if pending_update:
                pending_update.pending_clarification = True
                pending_update.save()
                # Notify trainer for clarification
                trainer = pending_update.updated_by
                if trainer:
                    Notification.objects.create(
                        user=trainer,
                        message=f"Your update for device {pending_update.serial_number} was rejected. Please provide clarification.",
                        content_type=ContentType.objects.get_for_model(PendingUpdate),
                        object_id=pending_update.pk
                    )
                # Mark notifications as read for admins only
                content_type = ContentType.objects.get_for_model(PendingUpdate)
                Notification.objects.filter(
                    content_type=content_type,
                    object_id=pk,
                    user__is_superuser=True,
                    user__is_trainer=False,
                    is_read=False
                ).update(is_read=True, responded_by=request.user)
                messages.success(request, f"Update for device {pending_update.serial_number} sent back for clarification.")
            else:
                # For new import requests, mark as pending clarification (add pending_clarification to Import if needed)
                import_instance.pending_clarification = True  # Ensure this field exists in Import model
                import_instance.save()
                # Notify trainer for clarification
                trainer = import_instance.added_by
                if trainer:
                    Notification.objects.create(
                        user=trainer,
                        message=f"Your import request for device {import_instance.serial_number} was rejected. Please provide clarification.",
                        content_type=ContentType.objects.get_for_model(Import),
                        object_id=import_instance.pk
                    )
                # Mark notifications as read for admins only
                content_type = ContentType.objects.get_for_model(Import)
                Notification.objects.filter(
                    content_type=content_type,
                    object_id=pk,
                    user__is_superuser=True,
                    user__is_trainer=False,
                    is_read=False
                ).update(is_read=True, responded_by=request.user)
                messages.success(request, f"Import request for device {import_instance.serial_number} sent back for clarification.")
            return redirect('display_unapproved_imports')
    return redirect('display_unapproved_imports')

@login_required
@user_passes_test(lambda u: u.is_superuser and not u.is_trainer)
def import_approve_all(request):
    if request.method == 'POST':
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
            page_number = int(page_number) if page_number else 1
        except ValueError:
            page_number = 1

        data = Import.objects.filter(is_approved=False, is_disposed=False)
        if search_query:
            query = (
                Q(centre__name__icontains=search_query) |
                Q(centre__centre_code__icontains=search_query) |
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

        paginator = Paginator(data, items_per_page)
        try:
            data_on_page = paginator.page(page_number)
        except PageNotAnInteger:
            data_on_page = paginator.page(1)
        except EmptyPage:
            data_on_page = paginator.page(paginator.num_pages)

        approved_count = 0
        with transaction.atomic():
            for item in data_on_page:
                pending_update = PendingUpdate.objects.filter(import_record=item).order_by('-created_at').first()
                if pending_update:
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
                    content_type = ContentType.objects.get_for_model(PendingUpdate)
                    Notification.objects.filter(
                        content_type=content_type,
                        object_id=pending_update.pk,
                        user__is_superuser=True,
                        user__is_trainer=False,
                        is_read=False
                    ).update(is_read=True, responded_by=request.user)
                    approved_count += 1
                elif not item.is_approved:
                    item.is_approved = True
                    item.approved_by = request.user
                    item.save()
                    content_type = ContentType.objects.get_for_model(Import)
                    Notification.objects.filter(
                        content_type=content_type,
                        object_id=item.pk,
                        user__is_superuser=True,
                        user__is_trainer=False,
                        is_read=False
                    ).update(is_read=True, responded_by=request.user)
                    approved_count += 1

        if approved_count > 0:
            messages.success(request, f"{approved_count} device(s) approved successfully.")
        else:
            messages.info(request, "No unapproved devices to approve on this page.")
        
        redirect_url = reverse('display_unapproved_imports')
        query_params = [f"page={page_number}", f"items_per_page={items_per_page}"]
        if search_query:
            query_params.append(f"search={search_query}")
        redirect_url += "?" + "&".join(query_params)
        return redirect(redirect_url)
    return redirect('display_unapproved_imports')

@login_required
@user_passes_test(lambda u: not u.is_trainer)
def import_delete(request, pk):
    import_instance = get_object_or_404(Import, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            serial_number = import_instance.serial_number
            import_instance.delete()
            content_type = ContentType.objects.get_for_model(Import)
            Notification.objects.filter(
                content_type=content_type,
                object_id=pk,
                user__is_superuser=True,
                user__is_trainer=False,
                is_read=False
            ).update(is_read=True, responded_by=request.user)
            messages.success(request, f"Device {serial_number} deleted successfully.")
        return redirect('display_approved_imports')
    return redirect('display_approved_imports')

@login_required
def notifications_view(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    # For admins, exclude notifications already responded to unless it's an unresponded approval request
    if request.user.is_superuser and not request.user.is_trainer:
        content_types = [ContentType.objects.get_for_model(Import), ContentType.objects.get_for_model(PendingUpdate)]
        notifications = notifications.exclude(
            responded_by__isnull=False
        ).filter(
            content_type__in=content_types,
            is_read=False
        ) | notifications.filter(
            responded_by__isnull=True,
            content_type__in=content_types,
            is_read=False
        )
    return render(request, 'notifications.html', {'notifications': notifications})

@login_required
@user_passes_test(lambda u: u.is_trainer)
def update_pending_clarification(request, pk):
    pending_update = get_object_or_404(PendingUpdate, pk=pk, import_record__pending_updates__pending_clarification=True)
    if request.method == 'POST':
        # Assume a form is submitted with updated fields
        pending_update.centre_id = request.POST.get('centre')
        pending_update.department_id = request.POST.get('department')
        pending_update.hardware = request.POST.get('hardware')
        pending_update.system_model = request.POST.get('system_model')
        pending_update.processor = request.POST.get('processor')
        pending_update.ram_gb = request.POST.get('ram_gb')
        pending_update.hdd_gb = request.POST.get('hdd_gb')
        pending_update.serial_number = request.POST.get('serial_number')
        pending_update.assignee_first_name = request.POST.get('assignee_first_name')
        pending_update.assignee_last_name = request.POST.get('assignee_last_name')
        pending_update.assignee_email_address = request.POST.get('assignee_email_address')
        pending_update.device_condition = request.POST.get('device_condition')
        pending_update.status = request.POST.get('status')
        pending_update.date = request.POST.get('date')
        pending_update.reason_for_update = request.POST.get('reason_for_update')
        pending_update.pending_clarification = False
        pending_update.save()
        # Notify all admins
        admins = CustomUser.objects.filter(is_superuser=True, is_trainer=False)
        for admin in admins:
            Notification.objects.create(
                user=admin,
                message=f"Updated pending clarification for device {pending_update.serial_number} by {request.user.username}.",
                content_type=ContentType.objects.get_for_model(PendingUpdate),
                object_id=pending_update.pk
            )
        # Mark trainer's clarification notification as read
        clarification_notification = Notification.objects.filter(
            user=request.user,
            content_type=ContentType.objects.get_for_model(PendingUpdate),
            object_id=pending_update.pk,
            is_read=False
        ).first()
        if clarification_notification:
            clarification_notification.is_read = True
            clarification_notification.save()
        messages.success(request, "Update submitted for approval.")
        return redirect('/dashboard/')
    return render(request, 'update_pending_clarification.html', {'pending_update': pending_update})