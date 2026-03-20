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
    staff_signature_png = models.TextField(blank=True, null=True, help_text="Optional saved IT signature (base64 PNG data URL)")
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
        ('smart_phone', 'Smart Phones'),
        ('desk_phone', 'Desk Phones'),
        ('ipad', 'iPads'),
        ('tablet', 'Tablets'),
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
    is_active = models.BooleanField(default=True, help_text="If false, the device is inactive (e.g., under repair) and actions are blocked.")
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


class DeviceRepair(models.Model):
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_WRITTEN_OFF = "written_off"

    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_WRITTEN_OFF, "Written off"),
    ]

    device = models.ForeignKey("Import", on_delete=models.CASCADE, related_name="repairs")

    month = models.CharField(max_length=20, blank=True, null=True)
    date_of_repair = models.DateField(blank=True, null=True)

    centre_department = models.CharField(max_length=255, blank=True, null=True)
    owner = models.CharField(max_length=255, blank=True, null=True)
    model = models.CharField(max_length=255, blank=True, null=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)

    reported_by = models.CharField(max_length=255, blank=True, null=True)
    issue_description = models.TextField()
    repair_action_taken = models.TextField(blank=True, null=True)
    technician_responsible = models.CharField(max_length=255, blank=True, null=True)
    cost_kes = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS)
    notes = models.TextField(blank=True, null=True)
    external_repair = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="repairs_created",
    )
    assigned_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="repairs_assigned",
        help_text="Current IT officer responsible for continuing this repair.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-date_of_repair", "-created_at"]

    @property
    def is_open(self) -> bool:
        return self.status == self.STATUS_IN_PROGRESS

        
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

    # ========== OPTIONAL UPLOADED PDF ==========
    # For legacy/external UAFs that were signed outside the system.
    uploaded_uaf_pdf = models.FileField(upload_to="uaf_uploads/%Y/%m/", blank=True, null=True)
    uploaded_uaf_uploaded_at = models.DateTimeField(blank=True, null=True)
    uploaded_uaf_uploaded_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_uafs",
    )

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
    category = models.CharField(max_length=200, choices=Import.CATEGORY_CHOICES, blank=True, null=True)
    device_name = models.CharField(max_length=100, blank=True, null=True)
    system_model = models.CharField(max_length=100, blank=True, null=True)
    processor = models.CharField(max_length=100, blank=True, null=True)
    ram_gb = models.CharField(max_length=10, blank=True, null=True)
    hdd_gb = models.CharField(max_length=10, blank=True, null=True)
    serial_number = models.CharField(max_length=100)
    assignee_first_name = models.CharField(max_length=50, blank=True, null=True)
    assignee_last_name = models.CharField(max_length=50, blank=True, null=True)
    assignee_email_address = models.EmailField(blank=True, null=True)
    assignee = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pending_device_updates',
    )
    device_condition = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    reason_for_update = models.TextField()
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    pending_clarification = models.BooleanField(default=False)  # New field

    def _sync_from_import_record(self):
        if not self.import_record_id:
            return

        current = self.import_record

        if self.centre_id is None:
            self.centre = current.centre
        if self.department_id is None:
            self.department = current.department
        if not self.category:
            self.category = current.category
        if self.device_name is None:
            self.device_name = current.device_name
        if self.system_model is None:
            self.system_model = current.system_model
        if self.processor is None:
            self.processor = current.processor
        if self.ram_gb is None:
            self.ram_gb = current.ram_gb
        if self.hdd_gb is None:
            self.hdd_gb = current.hdd_gb
        if not self.serial_number:
            self.serial_number = current.serial_number
        if self.assignee_id is None:
            self.assignee = current.assignee
        if self.assignee_first_name is None:
            self.assignee_first_name = current.assignee_first_name
        if self.assignee_last_name is None:
            self.assignee_last_name = current.assignee_last_name
        if self.assignee_email_address is None:
            self.assignee_email_address = current.assignee_email_address
        if self.device_condition is None:
            self.device_condition = current.device_condition
        if self.status is None:
            self.status = current.status
        if self.date is None:
            self.date = current.date

    def save(self, *args, **kwargs):
        self._sync_from_import_record()
        super().save(*args, **kwargs)

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


class DeviceConfigurationType(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    applies_to_laptop = models.BooleanField(default=True)
    applies_to_desktop = models.BooleanField(default=True)
    applies_to_server = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class DeviceConfiguration(models.Model):
    device = models.ForeignKey(Import, on_delete=models.CASCADE, related_name='device_configurations')
    config_type = models.ForeignKey(DeviceConfigurationType, on_delete=models.CASCADE, related_name='device_configurations')

    is_completed = models.BooleanField(default=False)
    completed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_device_configurations')
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [['device', 'config_type']]
        ordering = ['config_type__sort_order', 'config_type__name']

    def __str__(self):
        return f"{self.device.serial_number} - {self.config_type.name}"
