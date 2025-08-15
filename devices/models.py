from django.db import models
from django.contrib.auth.models import AbstractUser

class Centre(models.Model):
    name = models.CharField(max_length=300)
    centre_code = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return f"{self.name} ({self.centre_code})"

class CustomUser(AbstractUser):
    is_trainer = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=True)
    centre = models.ForeignKey('Centre', on_delete=models.SET_NULL, null=True, blank=True)
    
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='customuser_set',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
  
    def __str__(self):
        return self.username

class Import(models.Model):
    file = models.FileField(upload_to='uploads/', null=True, blank=True)
    centre = models.ForeignKey(Centre, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.CharField(max_length=500, blank=True, null=True)
    hardware = models.CharField(max_length=500, blank=True, null=True)
    system_model = models.CharField(max_length=500, blank=True, null=True)
    processor = models.CharField(max_length=500, blank=True, null=True)
    ram_gb = models.CharField(max_length=500, blank=True, null=True)
    hdd_gb = models.CharField(max_length=500, blank=True, null=True)
    serial_number = models.CharField(max_length=500, blank=True, null=True)
    assignee_first_name = models.CharField(max_length=500, blank=True, null=True)
    assignee_last_name = models.CharField(max_length=500, blank=True, null=True)
    assignee_email_address = models.CharField(max_length=500, blank=True, null=True)
    device_condition = models.CharField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=500, blank=True, null=True)
    date = models.DateField(auto_now=True, null=True, blank=True)
    added_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='added_imports', default=None)
    approved_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_imports')
    is_approved = models.BooleanField(default=False)
    reason_for_update = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.added_by and self.added_by.is_trainer and not self.pk:
            self.is_approved = False
        print(f"Saving Import instance: {self.__dict__}")
        super().save(*args, **kwargs)

    @property
    def display_field(self):
        return self.assignee_email_address

    def __str__(self):
        return f"{self.centre.centre_code if self.centre else 'No Centre'} - {self.serial_number or 'No Serial'}"

class Report(models.Model):
    def __str__(self):
        return "Report"