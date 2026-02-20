from django.db import models
from django.conf import settings
from devices.models import Import


class PPMPeriod(models.Model):
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    # Planned activities for the whole period (baseline for audit)
    activities = models.ManyToManyField("PPMActivity", blank=True, related_name="periods")

    def save(self, *args, **kwargs):
        if self.is_active:
            PPMPeriod.objects.filter(is_active=True).exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PPMActivity(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class PPMTask(models.Model):
    """
    One PPM task per device per period.
    This simplified structure stores the selected/performed activities directly on the task.
    """
    device = models.ForeignKey(Import, on_delete=models.CASCADE, related_name="ppm_tasks")
    period = models.ForeignKey(PPMPeriod, on_delete=models.CASCADE, related_name="tasks")

    # Activities selected/performed for THIS device in this period
    activities = models.ManyToManyField(PPMActivity, blank=True, related_name="tasks")
    no_ppm_activity_performed = models.BooleanField(default=False)

    # Task closure fields (optional)
    completed_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ppm_tasks_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["device", "period"], name="uniq_ppm_task_device_period")
        ]

    def __str__(self):
        return f"PPM Task for {self.device.serial_number} - {self.period.name}"

    @property
    def planned_activities_qs(self):
        """
        Planned checklist (prefer task-specific activities if set, else fallback to period activities).
        Useful for reporting and ensuring each device follows the period baseline when task.activities is empty.
        """
        qs = self.activities.all()
        return qs if qs.exists() else self.period.activities.all()