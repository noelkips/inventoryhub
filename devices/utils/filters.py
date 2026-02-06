# your_project/utils/filters.py
from django.db.models import Q

KNOWN_device_name_KEYWORDS = [
    'laptop', 'monitor', 'system unit', 'printer',
    'router', 'switch', 'server', 'n-computing', 'television'
]

def unknown_device_name_q():
    """
    Matches devices whose `device_name` field:
      • is NULL
      • is empty string
      • does NOT contain any known keyword (case-insensitive)
    """
    known = Q()
    for kw in KNOWN_device_name_KEYWORDS:
        known |= Q(device_name__icontains=kw)

    return Q(device_name__isnull=True) | Q(device_name='') | ~known