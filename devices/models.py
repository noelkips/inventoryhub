from django.db import models

class Import(models.Model):
    file = models.FileField(upload_to='uploads/', null=True, blank=True)
    centre = models.CharField(max_length=500, blank=True, null=True)
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
    date = models.DateField(auto_now=True)

    def save(self, *args, **kwargs):
        print(f"Saving Import instance: {self.__dict__}")
        super().save(*args, **kwargs)

    @property
    def display_field(self):
        return self.assignee_email_address

    def __str__(self):
        return f"{self.centre} - {self.serial_number}"

class Report(models.Model):
    def __str__(self):
        return "Report"