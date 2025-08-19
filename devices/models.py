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
    centre = models.ForeignKey(Centre, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    hardware = models.CharField(max_length=100, blank=True, null=True)
    system_model = models.CharField(max_length=100, blank=True, null=True)
    processor = models.CharField(max_length=100, blank=True, null=True)
    ram_gb = models.CharField(max_length=10, blank=True, null=True)
    hdd_gb = models.CharField(max_length=10, blank=True, null=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    assignee_first_name = models.CharField(max_length=50, blank=True, null=True)
    assignee_last_name = models.CharField(max_length=50, blank=True, null=True)
    assignee_email_address = models.EmailField(blank=True, null=True)
    device_condition = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    added_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='imports_added')
    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='imports_approved')
    is_approved = models.BooleanField(default=False)
    reason_for_update = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.serial_number} ({self.centre.name if self.centre else 'No Centre'})"

class PendingUpdate(models.Model):
    import_record = models.ForeignKey(Import, on_delete=models.CASCADE, related_name='pending_updates')
    centre = models.ForeignKey(Centre, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    hardware = models.CharField(max_length=100, blank=True, null=True)
    system_model = models.CharField(max_length=100, blank=True, null=True)
    processor = models.CharField(max_length=100, blank=True, null=True)
    ram_gb = models.CharField(max_length=10, blank=True, null=True)
    hdd_gb = models.CharField(max_length=10, blank=True, null=True)
    serial_number = models.CharField(max_length=100)
    assignee_first_name = models.CharField(max_length=50, blank=True, null=True)
    assignee_last_name = models.CharField(max_length=50, blank=True, null=True)
    assignee_email_address = models.EmailField(blank=True, null=True)
    device_condition = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    reason_for_update = models.TextField()
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pending update for {self.import_record.serial_number} by {self.updated_by}"
    
class Report(models.Model):
    def __str__(self):
        return "Report"