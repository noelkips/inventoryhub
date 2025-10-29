from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta
from devices.models import Centre, Department

User = get_user_model()

# ============ MISSION CRITICAL ASSETS ============
class MissionCriticalAsset(models.Model):
    CATEGORY_CHOICES = [
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
    location_scope = models.CharField(max_length=255, help_text="Location/Scope (e.g., HQ & Data Centers)")
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
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
    ]
    
    work_plan = models.ForeignKey(WorkPlan, on_delete=models.CASCADE, related_name='tasks')
    day = models.CharField(max_length=10, choices=DAY_CHOICES)
    task_description = models.TextField(help_text="Description of the task")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['day', 'created_at']
        verbose_name = 'Work Plan Task'
        verbose_name_plural = 'Work Plan Tasks'
    
    def __str__(self):
        return f"{self.work_plan.user.username} - {self.day}: {self.task_description[:50]}"


class WorkPlanTaskComment(models.Model):
    task = models.ForeignKey(WorkPlanTask, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    comment = models.TextField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Comment by {self.user.username} on {self.task}"


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
