from itinventory import settings
from .models import Notification

def notification_count(request):
    if request.user.is_authenticated:
        qs = Notification.objects.filter(user=request.user).order_by('-created_at')
        unread_count = qs.filter(is_read=False).count()
        recent_notifications = list(qs[:8])
        return {
            # Backwards-compatible key
            'notification_count': unread_count,
            # Preferred keys used by templates/JS
            'unread_count': unread_count,
            'recent_notifications': recent_notifications,
        }
    return {'notification_count': 0, 'unread_count': 0, 'recent_notifications': []}


def global_settings(request):
    from itinventory import settings
    
    return {
        'DB_NAME_CONFIG': settings.DB_NAME_CONFIG,
       
    }
