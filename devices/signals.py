from django.contrib.auth.models import Group
from .models import PendingUpdate, Import, Notification, CustomUser
import threading


from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

# Configure logging



@receiver(post_save, sender=PendingUpdate)
def notify_admins_on_submission(sender, instance, created, **kwargs):
    if created:
        try:
            content_type = ContentType.objects.get_for_model(PendingUpdate)
            admins = CustomUser.objects.filter(is_superuser=True, is_trainer=False)
            message = f"New device update pending approval for serial: {instance.serial_number} by {instance.updated_by.username} (Reason: {instance.reason_for_update})"
            for admin in admins:
                Notification.objects.create(
                    user=admin,
                    message=message,
                    content_type=content_type,
                    object_id=instance.pk
                )
        except ContentType.DoesNotExist as e:
            pass


@receiver(post_save, sender=Import)
def notify_trainer_on_approval(sender, instance, **kwargs):
    if instance.is_approved and instance.approved_by:
        pending = instance.pending_updates.order_by('-created_at').first()
        if pending and pending.updated_by:
            try:
                content_type = ContentType.objects.get_for_model(Import)
                trainer = pending.updated_by
                message = f"Your device update for serial: {instance.serial_number} has been approved by {instance.approved_by.username}"
                Notification.objects.create(
                    user=trainer,
                    message=message,
                    content_type=content_type,
                    object_id=instance.pk
                )
            except ContentType.DoesNotExist as e:
                pass


@receiver(pre_save, sender=Import)
def set_history_user(sender, instance, **kwargs):
    request = getattr(threading.local(), 'request', None)
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        instance._history_user = request.user