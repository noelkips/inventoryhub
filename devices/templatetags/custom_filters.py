from django import template
from devices.models import Import  # Replace 'yourapp' with actual app name

register = template.Library()

@register.filter
def get_category_value(display_name):
    """Reverse lookup: given display name (e.g. 'Laptop'), return value ('laptop')"""
    for value, label in Import.CATEGORY_CHOICES:
        if label == display_name:
            return value
    return ''  # fallback