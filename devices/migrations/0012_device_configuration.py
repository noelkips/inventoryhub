from django.db import migrations, models
import django.db.models.deletion


def seed_default_configuration_types(apps, schema_editor):
    DeviceConfigurationType = apps.get_model('devices', 'DeviceConfigurationType')

    defaults = [
        ("All in Google", "Account + files synced to Google where applicable"),
        ("Windows Installed", ""),
        ("Windows Activated", ""),
        ("Device Cleaned", ""),
        ("Domain/WorkGroup", ""),
        ("Admin/User Accounts", ""),
        ("Background Apps Off", ""),
        ("WiFi Sharing Off", ""),
        ("Chrome Enterprise", ""),
        ("Homepage & Defaults", ""),
        ("Google Drive", ""),
        ("Offline Drive", ""),
        ("Office Installed", ""),
        ("Office Activated", ""),
        ("AnyDesk Installed", ""),
        ("Printer Setup", ""),
        ("UAF Signed", ""),
        ("Inventoria Updated", ""),
        ("Allocated in Inventoria", ""),
        ("Final Confirm", ""),
    ]

    for idx, (name, description) in enumerate(defaults, start=1):
        DeviceConfigurationType.objects.get_or_create(
            name=name,
            defaults={
                "description": description,
                "sort_order": idx * 10,
                "is_active": True,
                "applies_to_laptop": True,
                "applies_to_desktop": True,
                "applies_to_server": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("devices", "0011_remove_devicelog_ppm_attempt"),
    ]

    operations = [
        migrations.CreateModel(
            name="DeviceConfigurationType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("description", models.TextField(blank=True, null=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("applies_to_laptop", models.BooleanField(default=True)),
                ("applies_to_desktop", models.BooleanField(default=True)),
                ("applies_to_server", models.BooleanField(default=True)),
            ],
            options={"ordering": ["sort_order", "name"]},
        ),
        migrations.CreateModel(
            name="DeviceConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_completed", models.BooleanField(default=False)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "completed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="completed_device_configurations",
                        to="devices.customuser",
                    ),
                ),
                (
                    "config_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="device_configurations",
                        to="devices.deviceconfigurationtype",
                    ),
                ),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="device_configurations",
                        to="devices.import",
                    ),
                ),
            ],
            options={"ordering": ["config_type__sort_order", "config_type__name"], "unique_together": {("device", "config_type")}},
        ),
        migrations.RunPython(seed_default_configuration_types, migrations.RunPython.noop),
    ]

