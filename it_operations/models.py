from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta
from devices.models import Centre, Department
from django.core.exceptions import ValidationError

User = get_user_model()

# ============ MISSION CRITICAL ASSETS ============
class MissionCriticalAsset(models.Model):
    CATEGORY_CHOICES = [
        ('Application', 'Application'),
        ('Infrastructure', 'Infrastructure'),
        ('Network', 'Network'),
        ('Security', 'Security'),
        ('Storage', 'Storage'),
        ('Backup', 'Backup'),
        ('Power', 'Power'),
        ('Cooling', 'Cooling'),
        ('Other', 'Other'),

    ]
    
    CRITICALITY_LEVEL_CHOICES = [
        ('Critical', 'Critical'),
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
    ]
    
    name = models.CharField(max_length=255, help_text="Name/Description of the asset")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    location_scope = models.CharField(
    max_length=255,
    blank=True,           
    null=True,           
    help_text="Location/Scope (e.g., HQ & Data Centers)"
)
    purpose_function = models.TextField(help_text="Purpose/Function of the asset")
    dependency_linked_system = models.TextField(blank=True, null=True, help_text="Dependency/Linked System")
    backup_recovery_method = models.TextField(help_text="Backup/Recovery Method")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='mission_critical_assets')
    criticality_level = models.CharField(max_length=20, choices=CRITICALITY_LEVEL_CHOICES)
    notes = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='mission_critical_assets_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Mission Critical Asset'
        verbose_name_plural = 'Mission Critical Assets'
    
    def __str__(self):
        return f"{self.name} ({self.criticality_level})"


# ============ BACKUP REGISTRY ============
class BackupRegistry(models.Model):
    SYSTEM_CHOICES = [
        ('quickbooks', 'QuickBooks'),
        ('smartcare', 'SmartCare'),
        ('inventory', 'Inventory Systems'),
    ]
    
    system = models.CharField(max_length=50, choices=SYSTEM_CHOICES, help_text="System/Software being backed up")
    centre = models.ForeignKey(Centre, on_delete=models.CASCADE, related_name='backup_registries')
    date = models.DateField(auto_now_add=True)
    done_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='backups_performed')
    comments = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date']
        verbose_name = 'Backup Registry'
        verbose_name_plural = 'Backup Registries'
    
    def __str__(self):
        return f"{self.get_system_display()} - {self.centre.name} ({self.date})"



from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta
from devices.models import Centre, Department
from django.core.exceptions import ValidationError

User = get_user_model()

# ============ WORK PLAN (The Container for the Week) ============
class WorkPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='work_plans')
    
    # We store the start of the week to identify the "Plan Period"
    week_start_date = models.DateField(help_text="The Monday date of this work week")
    week_end_date = models.DateField(help_text="The Saturday date of this work week")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-week_start_date']
        unique_together = ('user', 'week_start_date') # One plan per user per week
        verbose_name = 'Work Plan'
    
    def __str__(self):
        return f"{self.user.username} - Week of {self.week_start_date}"

    def save(self, *args, **kwargs):
        # Auto-calculate week_end_date if not set (Monday + 5 days = Saturday)
        if not self.week_end_date and self.week_start_date:
            self.week_end_date = self.week_start_date + timedelta(days=5)
        super().save(*args, **kwargs)

    def is_editable(self):
        """
        Legacy method: Kept to avoid breaking other parts, but logic is now split.
        """
        return self.can_add_tasks

    @property
    def can_add_tasks(self):
        """
        Strict Rule: Adding NEW tasks is locked after Monday 10:00 AM of the current week.
        """
        now = timezone.now()
        # Deadline is the Monday of this week at 10:00 AM
        deadline_dt = datetime.combine(self.week_start_date, datetime.min.time()) + timedelta(hours=10)
        deadline = timezone.make_aware(deadline_dt)
        
        # If we are past the deadline, return False
        return now <= deadline

    @property
    def status_summary(self):
        """Returns a dictionary of task counts for reports"""
        total = self.tasks.count()
        completed = self.tasks.filter(status='Completed').count()
        not_done = self.tasks.filter(status='Not Done').count()
        return {
            'total': total, 
            'completed': completed, 
            'not_done': not_done
        }


class PublicHoliday(models.Model):
    """
    Manages Kenyan Public Holidays to disable dates in the calendar.
    """
    name = models.CharField(max_length=100)
    date = models.DateField(unique=True)
    
    def __str__(self):
        return f"{self.name} - {self.date}"


# ============ WORK PLAN TASK (The Specific Item) ============
class WorkPlanTask(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),         # Default when created
        ('Completed', 'Completed'),     # User manually marks this
        ('Rescheduled', 'Rescheduled'), # User moved it
        ('Not Done', 'Not Done'),       # System marks this if week passes
    ]

    work_plan = models.ForeignKey(WorkPlan, on_delete=models.CASCADE, related_name='tasks')
    
    # REPLACED 'day' string with actual DateField
    date = models.DateField(help_text="Specific calendar date for this task")
    is_leave = models.BooleanField(default=False, help_text="Is the staff member on leave this day?")
    # =========================================================
    # EACH TASK HAS ITS OWN SET OF THESE FIELDS AS REQUESTED:
    # =========================================================
    task_name = models.CharField(max_length=255, help_text="What is the specific task?")
    
    # Location Info
    centre = models.ForeignKey(Centre, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)

    
    # People Involved (Specific to this task)
    collaborators = models.ManyToManyField(
        User, 
        blank=True, 
        related_name='collaborating_tasks',
        help_text="Internal IT Staff or Trainers working on this specific task"
    )
    
    other_parties = models.TextField(
        blank=True, 
        null=True, 
        help_text="External vendors, non-IT staff, or other stakeholders involved"
    )
    
    # Execution Details (Specific to this task)
    resources_needed = models.TextField(
        blank=True, 
        null=True, 
        help_text="Hardware, Software, Transport, Budget, etc."
    )
    
    target = models.CharField(
        max_length=500, 
        blank=True, 
        null=True, 
        help_text="Measurable outcome (e.g., '50 PCs serviced')"
    )
    
    comments = models.TextField(blank=True, null=True, help_text="User remarks or justification")
    reschedule_reason = models.TextField(
    blank=True, 
    null=True,
    help_text="Reason for rescheduling this task (required when rescheduling)"
)
    # Status Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    status_updated_at = models.DateTimeField(auto_now=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_tasks')

    class Meta:
        ordering = ['date', 'created_at']
        verbose_name = 'Work Plan Task'

    def clean(self):
        super().clean()
        
        if self.work_plan:
            # Only enforce date within week
            if not (self.work_plan.week_start_date <= self.date <= self.work_plan.week_end_date):
                raise ValidationError(
                    f"Task date {self.date} must be between {self.work_plan.week_start_date} and {self.work_plan.week_end_date}"
                )

    def save(self, *args, **kwargs):
        self.full_clean() # Run the validation above before saving
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.task_name} ({self.date})"

    @property
    def display_status(self):
        """
        Frontend Logic for 'Active':
        If status is 'Pending' AND the date has arrived (is today or in current week),
        display as 'Active' to the user.
        """
        if self.status == 'Pending':
            today = timezone.now().date()
            # If today is within the plan's week, we consider it Active
            if self.work_plan.week_start_date <= today <= self.work_plan.week_end_date:
                return 'Active'
        return self.status

    @property
    def is_overdue(self):
        """Logic #4: Check if task is Pending and date is in the past."""
        return self.status == 'Pending' and self.date < timezone.now().date()



# ============ INCIDENT REPORT ============

def get_next_incident_number():
    """
    Generates the next incident number based on the last one, e.g., MOH-IT-2025-001
    """
    last_incident = IncidentReport.objects.all().order_by('id').last()
    year = timezone.now().year
    
    if not last_incident:
        return f'MOH-IT-{year}-001'
    
    try:
        # Assumes format MOH-IT-YEAR-XXX
        last_number_int = int(last_incident.incident_number.split('-')[-1])
        new_number_int = last_number_int + 1
        return f'MOH-IT-{year}-{new_number_int:03d}'
    except (ValueError, IndexError):
        # Fallback if parsing fails
        return f'MOH-IT-{year}-001'

class IncidentReport(models.Model):
    # Section 1: Report Info
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='incident_reports_created')
    reporter_title_role = models.CharField(max_length=255, help_text="Title / Role of the person reporting")
    incident_number = models.CharField(max_length=50, unique=True, default=get_next_incident_number)
    date_of_report = models.DateTimeField(auto_now_add=True)
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('In Progress', 'In Progress'),
        ('Closed', 'Closed'),
        ('Resolved', 'Resolved'),
    ]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Open')
    
    # NEW: Collaborators
    collaborators = models.ManyToManyField(User, related_name='incident_collaborations', blank=True)
    
    # Section 2: Incident Info
    incident_type = models.CharField(max_length=255, help_text="e.g., INTERNET OUTAGE, SERVER DOWN")
    date_of_incident = models.DateTimeField(
        help_text="Date and time the incident occurred",
        blank=True,  # REQUIRED FOR FORM SUBMISSION
        null=True    # REQUIRED FOR DATABASE
    )
    location = models.CharField(max_length=255, help_text="e.g., BUSTANI (CEO'S RESIDENCE)")
    specific_area = models.CharField(max_length=255, blank=True, null=True, help_text="Specific area (if applicable)")
    
    # Section 3: Description
    description = models.TextField(help_text="Detailed description of the incident")
    
    # Section 4: Parties Involved (as a text block)
    parties_involved = models.TextField(blank=True, null=True, help_text="Name / Role / Contact / Statement of parties involved")

    # Section 5: Witnesses (as a text block)
    witnesses = models.TextField(blank=True, null=True, help_text="Name / Role / Contact of witnesses")
    
    # Section 6: Immediate Actions
    immediate_actions_taken = models.TextField(blank=True, null=True, help_text="Immediate actions taken")
    
    # Section 7: Reported To
    reported_to = models.CharField(max_length=255, blank=True, null=True, help_text="Name/Role of person(s) the incident was reported to")
    
    # Section 8: Follow-up
    follow_up_actions_required = models.TextField(blank=True, null=True, help_text="Any follow-up actions required")
    
    # Section 9: Notes
    additional_notes = models.TextField(blank=True, null=True, help_text="Additional notes or recommendations")
    
    class Meta:
        ordering = ['-date_of_incident']
        verbose_name = 'Incident Report'
        verbose_name_plural = 'Incident Reports'
    
    def __str__(self):
        return self.incident_number

