from django.db import models
from django.conf import settings
from devices.models import Import, Centre

class PPMPeriod(models.Model):
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    activities = models.ManyToManyField('PPMActivity', blank=True)

    def save(self, *args, **kwargs):
        if self.is_active:
            # Deactivate all other periods
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
    device = models.ForeignKey(Import, on_delete=models.CASCADE, related_name='ppm_tasks')
    period = models.ForeignKey(PPMPeriod, on_delete=models.CASCADE)
    activities = models.ManyToManyField(PPMActivity)
    completed_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PPM Task for {self.device.serial_number} - {self.period.name}"