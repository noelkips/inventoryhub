from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta
from devices.models import Centre, Department


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


# ============ WORK PLAN ============
class WorkPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='work_plans')
    week_start_date = models.DateField(help_text="Monday of the week")
    week_end_date = models.DateField(help_text="Saturday of the week (Sunday excluded)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-week_start_date']
        unique_together = ('user', 'week_start_date')
        verbose_name = 'Work Plan'
        verbose_name_plural = 'Work Plans'
    
    def __str__(self):
        return f"{self.user.username} - Week of {self.week_start_date}"
    
    def is_editable(self):
        """Check if work plan can still be edited (before Monday 10 AM of next week)"""
        now = timezone.now()
        next_monday = self.week_start_date + timedelta(days=7)
        deadline = timezone.make_aware(datetime.combine(next_monday, datetime.min.time()).replace(hour=10))
        return now < deadline
    
    def is_submitted(self):
        """Check if work plan has tasks"""
        return self.tasks.exists()
    
    def get_missing_days(self):
        """Get days without tasks"""
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        days_with_tasks = set(self.tasks.values_list('day', flat=True).distinct())
        return [day for day in days if day not in days_with_tasks]
    
    def get_current_week_status(self):
        """Determine if this is current, past, or future week"""
        today = timezone.now().date()
        if self.week_start_date <= today <= self.week_end_date:
            return 'current'
        elif today > self.week_end_date:
            return 'past'
        else:
            return 'future'


class WorkPlanTask(models.Model):
    DAY_CHOICES = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
    ]
    
    STATUS_CHOICES = [
        ('Completed', 'Completed'),
        ('Not Completed', 'Not Completed'),
        ('Not Done', 'Not Done'),
    ]
    
    work_plan = models.ForeignKey(WorkPlan, on_delete=models.CASCADE, related_name='tasks')
    day = models.CharField(max_length=10, choices=DAY_CHOICES)
    
    task_name = models.CharField(max_length=255, help_text="Task name/title")
    centre = models.ForeignKey(Centre, on_delete=models.SET_NULL, null=True, blank=True, help_text="Centre/Location (optional)")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, help_text="Department (optional)")
    
    human_resources = models.ManyToManyField(User, blank=True, related_name='assigned_tasks', help_text="Assigned staff members")
    
    items_needed = models.CharField(max_length=500, blank=True, null=True, help_text="Items/resources needed (e.g., Portal, Help desk)")
    
    comments = models.TextField(blank=True, null=True, help_text="Additional comments/details about the task")
    
    target = models.CharField(max_length=500, blank=True, null=True, help_text="Target/Desired outcome")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Not Done')
    
    status_updated_at = models.DateTimeField(auto_now=True)
    status_updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_status_updates')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_tasks')
    
    class Meta:
        ordering = ['day', 'created_at']
        verbose_name = 'Work Plan Task'
        verbose_name_plural = 'Work Plan Tasks'
    
    def __str__(self):
        return f"{self.work_plan.user.username} - {self.day}: {self.task_name}"
    
    def can_edit(self, user):
        """Check if task can be edited based on week status and user role"""
        work_plan = self.work_plan
        week_status = work_plan.get_current_week_status()
        
        # IT Manager can always edit
        if user.is_it_manager:
            return True
        
        # Original creator can edit current week
        if self.created_by == user and week_status == 'current':
            return True
        
        # Can't edit future weeks (locked at status "Not Done")
        if week_status == 'future':
            return False
        
        return False
    
    def auto_update_status(self):
        """Auto-update status based on week status"""
        work_plan = self.work_plan
        week_status = work_plan.get_current_week_status()
        
        if week_status == 'future':
            self.status = 'Not Done'
        elif week_status == 'past' and self.status != 'Completed':
            self.status = 'Not Done'
        
        return self.status
    
    def get_status_color(self):
        """Return color class based on status"""
        status_colors = {
            'Completed': 'bg-green-100 border-green-300 text-green-800',
            'Not Completed': 'bg-yellow-100 border-yellow-300 text-yellow-800',
            'Not Done': 'bg-red-100 border-red-300 text-red-800',
        }
        return status_colors.get(self.status, 'bg-gray-100')


class WorkPlanTaskComment(models.Model):
    task = models.ForeignKey(WorkPlanTask, on_delete=models.CASCADE, related_name='task_comments')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    comment = models.TextField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']


class WorkPlanActivity(models.Model):
    work_plan = models.ForeignKey(WorkPlan, on_delete=models.CASCADE, related_name='activities')
    day = models.CharField(max_length=10, choices=[
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
    ])
    activity = models.TextField(help_text="Description of the activity/task")
    status = models.CharField(max_length=20, choices=[
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
    ], default='Pending')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['day']
    
    def __str__(self):
        return f"{self.work_plan.user.username} - {self.day}: {self.activity[:50]}"


class WorkPlanComment(models.Model):
    work_plan = models.ForeignKey(WorkPlan, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    comment = models.TextField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Comment by {self.user.username} on {self.work_plan}"
    



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

