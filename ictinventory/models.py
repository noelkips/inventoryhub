from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from multiselectfield import MultiSelectField

# import datetime



    
    
class PPM(models.Model):
    DEVICE = (
        ('PC', 'PC'),
        ('Monitor', 'Monitor'),
        ('Keyboard', 'Keyboard'),
        ('Printer', 'Printer'),
        ('UPS', 'UPS'),
    )
    device = models.CharField(max_length=100, choices= DEVICE)
    device_name = models.CharField(max_length=100, unique=True)
    serial_number = models.CharField(max_length=100)
    device_model = models.CharField(max_length=500)
    # it_staff = models.ForeignKey(ITStaff, on_delete=models.CASCADE)
    assigned_by = models.CharField(max_length=100)
    assignee = models.CharField(max_length=100)
    centre = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    ACTIVITIES = (
        ('Complete static dust extraction', 'Complete static dust extraction'),
        ('Internal Cleaning', 'Internal Cleaning'),
        ('Clean and inspect power supply', 'Clean and inspect power supply'),
        ('Cable ties and arrangement', 'Cable ties and arrangement'),
        ('Inspect for loose screws and corrosion', 'Inspect for loose screws and corrosion'),
        ('Detailed external cleaning', 'Detailed external cleaning'),
        ('System test and verification', 'System test and verification'),
        ('Check for software loaded in the PC', 'Check for software loaded in the PC'),
        ('Load the latest antivirus on the PC', 'Load the latest antivirus on the PC'),
        ('Clean and lubricate moving parts/gears', 'Clean and lubricate moving parts/gears'),
        ('Test printer, working properly', 'Test printer, working properly'),
        ('Returned', 'Returned'),
        
    )
    # activities = models.CharField(max_length=500, choices=ACTIVITIES)
    activities = MultiSelectField(choices=ACTIVITIES, max_length=1000)
    issues = models.CharField(max_length=1000)
    recommendations = models.CharField(max_length=1000)
    date = models.DateTimeField(default=timezone.now)
    # date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.device_name
    
    
   



