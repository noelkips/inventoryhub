# your_project/utils/filters.py
from django.db.models import Q

KNOWN_HARDWARE_KEYWORDS = [
    'laptop', 'monitor', 'system unit', 'printer',
    'router', 'switch', 'server', 'n-computing', 'television'
]

def unknown_hardware_q():
    """
    Matches devices whose `hardware` field:
      • is NULL
      • is empty string
      • does NOT contain any known keyword (case-insensitive)
    """
    known = Q()
    for kw in KNOWN_HARDWARE_KEYWORDS:
        known |= Q(hardware__icontains=kw)

    return Q(hardware__isnull=True) | Q(hardware='') | ~known