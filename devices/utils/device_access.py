from devices.models import Employee


def can_manage_device_assignments(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False

    return bool(
        user.is_superuser
        or user.is_trainer
        or user.is_it_manager
        or user.is_senior_it_officer
        or (user.is_staff and not user.is_trainer)
    )


def can_clear_device_users(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False

    return bool(
        user.is_superuser
        or user.is_it_manager
        or user.is_senior_it_officer
        or (user.is_staff and not user.is_trainer)
    )


def assignment_employee_queryset(user):
    queryset = Employee.objects.filter(is_active=True)

    if getattr(user, "is_trainer", False):
        centre_id = getattr(user, "centre_id", None)
        if not centre_id:
            return queryset.none()
        queryset = queryset.filter(centre_id=centre_id)

    return queryset.order_by("last_name", "first_name")
