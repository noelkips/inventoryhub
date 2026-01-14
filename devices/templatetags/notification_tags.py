# devices/templatetags/notification_tags.py
from django import template
from django.contrib.contenttypes.models import ContentType

register = template.Library()

@register.filter
def is_instance(obj, model_name):
    if not obj:
        return False
    try:
        model = ContentType.objects.get(model=model_name.lower()).model_class()
        return isinstance(obj, model)
    except ContentType.DoesNotExist:
        return False