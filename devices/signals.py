from django.contrib.auth.models import Group
import threading

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import CustomUser, Import, Notification, PendingUpdate

# Configure logging

@receiver(post_save, sender=PendingUpdate)
def notify_admins_on_submission(sender, instance, created, **kwargs):
    if not created:
        return

    related_object = instance.import_record or instance
    content_type = ContentType.objects.get_for_model(related_object.__class__)
    requester_name = (
        instance.updated_by.get_full_name()
        if instance.updated_by and hasattr(instance.updated_by, "get_full_name")
        else getattr(instance.updated_by, "username", "Unknown user")
    ) or getattr(instance.updated_by, "username", "Unknown user")
    serial_number = instance.serial_number or getattr(instance.import_record, "serial_number", "Unknown serial")
    message = f"Update request for device {serial_number} by {requester_name} awaiting approval."

    reviewers = CustomUser.objects.filter(
        is_active=True,
        is_trainer=False,
    ).filter(
        Q(is_superuser=True) | Q(is_it_manager=True) | Q(is_senior_it_officer=True) | Q(is_staff=True)
    ).distinct()

    for reviewer in reviewers:
        notification = Notification.objects.filter(
            user=reviewer,
            content_type=content_type,
            object_id=related_object.pk,
            is_read=False,
        ).first()
        if notification:
            notification.message = message
            notification.responded_by = None
            notification.save(update_fields=["message", "responded_by"])
            continue

        Notification.objects.create(
            user=reviewer,
            message=message,
            content_type=content_type,
            object_id=related_object.pk,
        )


@receiver(post_save, sender=Import)
def notify_trainer_on_approval(sender, instance, **kwargs):
    if instance.is_approved and instance.approved_by:
        pending = instance.pending_updates.order_by('-created_at').first()
        if pending and pending.updated_by:
            content_type = ContentType.objects.get_for_model(Import)
            trainer = pending.updated_by
            approver_name = instance.approved_by.get_full_name() or instance.approved_by.username
            message = f"Your device update for serial: {instance.serial_number} has been approved by {approver_name}."

            notification = Notification.objects.filter(
                user=trainer,
                content_type=content_type,
                object_id=instance.pk,
                is_read=False,
            ).first()
            if notification:
                notification.message = message
                notification.responded_by = instance.approved_by
                notification.save(update_fields=["message", "responded_by"])
            else:
                Notification.objects.create(
                    user=trainer,
                    message=message,
                    content_type=content_type,
                    object_id=instance.pk
                )


@receiver(pre_save, sender=Import)
def set_history_user(sender, instance, **kwargs):
    request = getattr(threading.local(), 'request', None)
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        instance._history_user = request.user
