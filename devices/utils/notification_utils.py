from django.utils.text import Truncator

from devices.models import Import, Notification, PendingUpdate


WORKFLOW_REQUEST_MARKERS = (
    "awaiting approval",
    "pending approval",
    "was rejected",
    "provide clarification",
    "clarification",
)


def build_notification_preview(message, length=140):
    normalized = str(message or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    single_line = " ".join(part for part in normalized.splitlines() if part.strip())
    return Truncator(single_line).chars(length)


def is_workflow_request_notification(notification):
    model_name = getattr(getattr(notification, "content_type", None), "model", None)
    if model_name not in {"import", "pendingupdate"}:
        return False

    message = str(getattr(notification, "message", "") or "").lower()
    return any(marker in message for marker in WORKFLOW_REQUEST_MARKERS)


def _build_related_maps(notifications):
    import_ids = set()
    pending_update_ids = set()

    for notification in notifications:
        model_name = getattr(getattr(notification, "content_type", None), "model", None)
        if model_name == "import" and notification.object_id:
            import_ids.add(notification.object_id)
        elif model_name == "pendingupdate" and notification.object_id:
            pending_update_ids.add(notification.object_id)

    import_map = Import.objects.in_bulk(import_ids) if import_ids else {}
    pending_update_map = {
        pending.pk: pending
        for pending in PendingUpdate.objects.select_related("import_record").filter(pk__in=pending_update_ids)
    }
    return import_map, pending_update_map


def resolve_related_import(notification, *, import_map=None, pending_update_map=None):
    if hasattr(notification, "_resolved_import"):
        return notification._resolved_import

    related_import = None
    model_name = getattr(getattr(notification, "content_type", None), "model", None)

    if model_name == "import":
        if import_map is not None:
            related_import = import_map.get(notification.object_id)
        elif isinstance(getattr(notification, "related_object", None), Import):
            related_import = notification.related_object
    elif model_name == "pendingupdate":
        pending_update = None
        if pending_update_map is not None:
            pending_update = pending_update_map.get(notification.object_id)
        else:
            pending_update = getattr(notification, "related_object", None)
        related_import = getattr(pending_update, "import_record", None)

    notification._resolved_import = related_import
    return related_import


def sync_notification_state(notification, *, import_map=None, pending_update_map=None):
    related_import = resolve_related_import(
        notification,
        import_map=import_map,
        pending_update_map=pending_update_map,
    )

    if notification.is_read or not is_workflow_request_notification(notification):
        return notification

    if related_import is None or related_import.is_approved:
        update_fields = []
        notification.is_read = True
        update_fields.append("is_read")

        approved_by_id = getattr(related_import, "approved_by_id", None)
        if approved_by_id and notification.responded_by_id is None:
            notification.responded_by_id = approved_by_id
            update_fields.append("responded_by")

        notification.save(update_fields=update_fields)

    return notification


def sync_stale_workflow_notifications(user):
    unread_notifications = list(
        Notification.objects.filter(
            user=user,
            is_read=False,
            content_type__model__in=["import", "pendingupdate"],
        ).select_related("content_type", "responded_by")
    )

    candidates = [n for n in unread_notifications if is_workflow_request_notification(n)]
    if not candidates:
        return 0

    import_map, pending_update_map = _build_related_maps(candidates)
    notifications_to_update = []

    for notification in candidates:
        related_import = resolve_related_import(
            notification,
            import_map=import_map,
            pending_update_map=pending_update_map,
        )

        if related_import is None or related_import.is_approved:
            notification.is_read = True
            approved_by_id = getattr(related_import, "approved_by_id", None)
            if approved_by_id and notification.responded_by_id is None:
                notification.responded_by_id = approved_by_id
            notifications_to_update.append(notification)

    if notifications_to_update:
        Notification.objects.bulk_update(notifications_to_update, ["is_read", "responded_by"])

    return len(notifications_to_update)
