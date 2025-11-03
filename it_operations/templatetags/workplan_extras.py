# it_operations/templatetags/workplan_extras.py
from django import template

register = template.Library()

@register.filter
def length_of_status(queryset, status_name):
    """Return the number of objects in the queryset with the given status."""
    return queryset.filter(status=status_name).count()