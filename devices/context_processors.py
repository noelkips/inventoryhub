from itinventory import settings
from .models import Notification

def notification_count(request):
    if request.user.is_authenticated:
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return {'notification_count': count}
    return {'notification_count': 0}


def global_settings(request):
    from itinventory import settings
    
    return {
        'DB_NAME_CONFIG': settings.DATABASES['default']['NAME'],
       
    }