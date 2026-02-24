from datetime import timezone

from django.db import models
from itinventory import settings
from django.contrib.auth.models import AbstractUser
from simple_history.models import HistoricalRecords
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone

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
    is_it_manager = models.BooleanField(default=False, help_text="IT Manager - receives notifications for staff work plans")
    is_senior_it_officer = models.BooleanField(default=False, help_text="Senior IT Officer - receives notifications for trainer work plans")
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='customuser_set',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
  
    def __str__(self):
        return self.username
    
    def get_full_name(self):
        full_name = f"{self.first_name.capitalize()} {self.last_name.capitalize()}".strip()
        return full_name if full_name else self.username
    
class Employee(models.Model):
    """
    Lightweight person record — used for device assignees.
    Can later be replaced/extended with CustomUser if needed.
    """
    first_name     = models.CharField(max_length=100)
    last_name      = models.CharField(max_length=100)
    email          = models.EmailField(unique=True, blank=True, null=True)
    staff_number   = models.CharField(max_length=50, blank=True, null=True, unique=True)
    designation    = models.CharField(max_length=100, blank=True, null=True, help_text="Employee's job title/position")
    department     = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    centre         = models.ForeignKey(Centre, on_delete=models.SET_NULL, null=True, blank=True)
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['last_name', 'first_name']
        unique_together = [['first_name', 'last_name', 'email']]  # optional soft protection

    def __str__(self):
        return f"{self.first_name} {self.last_name}" + (f" ({self.email})" if self.email else "")

    @property
    def full_name(self):
        return f"{self.first_name.capitalize()} {self.last_name.capitalize()}".strip()




class Import(models.Model):
    CATEGORY_CHOICES = [
        ('laptop', 'Laptop'),
        ('system_unit', 'System Unit'),
        ('monitor', 'Monitor'),
        ('tv', 'Television'),
        ('networking_devices', 'Networking Devices'),
        ('printer', 'Printer'),
        ('n_computing', 'N Computing'),
        ('projector', 'projector'),
        ('gadget', 'Gadget'),
        ('access_point', 'Access Point'),
        ('power_backup_equipment', 'Power & Backup Equipment'),
        ('other', 'Other'),
    ]

    category = models.CharField(
        max_length=200,
        choices=CATEGORY_CHOICES,
        default='other',
        help_text='Device category/type'
    )
    centre = models.ForeignKey(Centre, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    device_name = models.CharField(max_length=100, blank=True, null=True)
    system_model = models.CharField(max_length=100, blank=True, null=True)
    processor = models.CharField(max_length=100, blank=True, null=True)
    ram_gb = models.CharField(max_length=10, blank=True, null=True)
    hdd_gb = models.CharField(max_length=10, blank=True, null=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    uaf_signed = models.BooleanField(default=False, help_text="Has UAF been signed for this device")


    # === Old fields (keep for migration phase) ===
    assignee_first_name = models.CharField(max_length=50, blank=True, null=True)
    assignee_last_name = models.CharField(max_length=50, blank=True, null=True)
    assignee_email_address = models.EmailField(blank=True, null=True)

    # === New fields ===
    assignee = models.ForeignKey(
        'Employee',  # assumes Employee model is in the same app
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_devices'
    )
    assignee_cache = models.CharField(
        max_length=255,
        blank=True,
        editable=False,
        help_text='Cached full name / staff number for search & reports'
    )

    device_condition = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(auto_now_add=True)
    added_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='imports_added')
    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='imports_approved')
    is_approved = models.BooleanField(default=False)
    reason_for_update = models.TextField(blank=True, null=True)
    is_disposed = models.BooleanField(default=False)
    disposal_reason = models.TextField(blank=True, null=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        # Optional: auto-update cache when saving (only if assignee is set)
        if self.assignee:
            self.assignee_cache = str(self.assignee)
        else:
            # fallback to old fields during transition
            parts = [self.assignee_first_name or '', self.assignee_last_name or '']
            name = ' '.join(filter(None, parts)).strip()
            self.assignee_cache = name if name else ''

        user = kwargs.pop('user', None)
        if user and not hasattr(self, '_history_user'):
            kwargs['update_fields'] = kwargs.get('update_fields', [])
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} ({self.centre.name if self.centre else 'No Centre'})"


class DeviceLog(models.Model):
    device = models.ForeignKey("Import", on_delete=models.CASCADE, related_name="logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="device_logs")
    message = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    # optional context
    ppm_task = models.ForeignKey("ppm.PPMTask", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

        
class DeviceAgreement(models.Model):
    device = models.ForeignKey("Import", on_delete=models.CASCADE, related_name='agreements')
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='device_agreements')

    # ========== ISSUANCE SECTION ==========
    # Issuance signatures (both as base64 PNG from canvas)
    issuance_user_signature_png = models.TextField(blank=True, help_text="Employee's drawn signature for issuance")
    issuance_it_signature_png = models.TextField(blank=True, help_text="IT staff's drawn signature for issuance")
    issuance_date = models.DateTimeField(null=True, blank=True)
    issuance_it_user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='issuance_agreements')
    user_signed_issuance = models.BooleanField(default=False)
    it_approved_issuance = models.BooleanField(default=False)

    # ========== CLEARANCE SECTION ==========
    # Clearance signatures (both as base64 PNG from canvas)
    clearance_user_signature_png = models.TextField(blank=True, help_text="Employee's drawn signature for clearance")
    clearance_it_signature_png = models.TextField(blank=True, help_text="IT staff's drawn signature for clearance")
    clearance_date = models.DateTimeField(null=True, blank=True)
    clearance_it_user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='clearance_agreements')
    clearance_remarks = models.TextField(blank=True, help_text="Optional remarks about device condition on return")
    user_signed_clearance = models.BooleanField(default=False)
    it_approved_clearance = models.BooleanField(default=False)

    is_archived = models.BooleanField(default=False)

    def __str__(self):
        return f"UAF for {self.device.serial_number} - {self.employee}"

    def archive(self):
        """Mark this agreement as archived."""
        self.is_archived = True
        self.save(update_fields=['is_archived'])

    class Meta:
        ordering = ['-issuance_date']

class DeviceUserHistory(models.Model):
    device = models.ForeignKey(Import, on_delete=models.CASCADE, related_name='user_history')
    # Keep old fields for now – consider switching to assignee FK later
    assignee_first_name = models.CharField(max_length=50, blank=True, null=True)
    assignee_last_name = models.CharField(max_length=50, blank=True, null=True)
    assignee_email_address = models.EmailField(blank=True, null=True)
    assigned_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='assignments_made')
    assigned_date = models.DateTimeField(auto_now_add=True)
    cleared_date = models.DateTimeField(null=True, blank=True)

    # Optional future improvement: add FK here too
    # assignee = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.assignee_first_name} {self.assignee_last_name} on {self.device.serial_number}"

class Clearance(models.Model):
    device = models.ForeignKey(Import, on_delete=models.CASCADE, related_name='clearances')
    cleared_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='clearances')
    clearance_date = models.DateField(auto_now_add=True)
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        self.device.assignee_first_name = None
        self.device.assignee_last_name = None
        self.device.assignee_email_address = None
        self.device.status = 'Available'
        self.device.department_id = 1
        self.device.reason_for_update = f"Device cleared by {self.cleared_by.username if self.cleared_by else 'Unknown'}"
        self.device.save(user=user)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Clearance for {self.device.serial_number} by {self.cleared_by}"


class PendingUpdate(models.Model):
    import_record = models.ForeignKey(Import, on_delete=models.CASCADE, related_name='pending_updates')
    centre = models.ForeignKey(Centre, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, default=1)
    device_name = models.CharField(max_length=100, blank=True, null=True)
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
    pending_clarification = models.BooleanField(default=False)  # New field

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
    responded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='responded_notifications')  # New field
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message}"