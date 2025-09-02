from django.db import models
from django.contrib.auth.models import AbstractUser
from simple_history.models import HistoricalRecords
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

class Centre(models.Model):
    name = models.CharField(max_length=300)
    centre_code = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return f"{self.name} ({self.centre_code})"
    

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    department_code = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return self.name


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
    # department = models.CharField(max_length=100, blank=True, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, default=1)
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
    date = models.DateField(auto_now_add=True)  # Auto-generate date on creation
    added_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='imports_added')
    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='imports_approved')
    is_approved = models.BooleanField(default=False)
    reason_for_update = models.TextField(blank=True, null=True)
    history = HistoricalRecords()  # Enable audit trail for all changes to Import

    def save(self, *args, **kwargs):
        # Set _history_user to the user from kwargs if provided
        if 'user' in kwargs:
            self._history_user = kwargs.pop('user')
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.serial_number} ({self.centre.name if self.centre else 'No Centre'})"

class Clearance(models.Model):
    device = models.ForeignKey(Import, on_delete=models.CASCADE, related_name='clearances')
    cleared_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='clearances')
    clearance_date = models.DateField(auto_now_add=True)
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Get the user from kwargs if provided
        user = kwargs.pop('user', None)
        # Clear assignee fields, set status to 'Available', and department to default (id=1)
        self.device.assignee_first_name = None
        self.device.assignee_last_name = None
        self.device.assignee_email_address = None
        self.device.status = 'Available'
        self.device.department_id = 1  # Set to default department (id=1)
        # Set reason_for_update for history tracking
        self.device.reason_for_update = f"Device cleared by {self.cleared_by.username if self.cleared_by else 'Unknown'}"
        # Pass the user to Import's save for history tracking
        self.device.save(user=user)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Clearance for {self.device.serial_number} by {self.cleared_by}"


class PendingUpdate(models.Model):
    import_record = models.ForeignKey(Import, on_delete=models.CASCADE, related_name='pending_updates')
    centre = models.ForeignKey(Centre, on_delete=models.SET_NULL, null=True, blank=True)
    # department = models.CharField(max_length=100, blank=True, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, default=1)
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



class Notification(models.Model):
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message}"