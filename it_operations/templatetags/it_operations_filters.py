from django import template

register = template.Library()

@register.filter
def mul(value, arg):
    """Multiply the value by the argument."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def split(value, arg):
    """Split a string by the given separator."""
    if isinstance(value, str):
        return value.split(arg)
    return value
