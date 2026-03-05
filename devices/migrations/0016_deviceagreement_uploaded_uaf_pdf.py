from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0015_historicalimport_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="deviceagreement",
            name="uploaded_uaf_pdf",
            field=models.FileField(blank=True, null=True, upload_to="uaf_uploads/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="deviceagreement",
            name="uploaded_uaf_uploaded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deviceagreement",
            name="uploaded_uaf_uploaded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="uploaded_uafs",
                to="devices.customuser",
            ),
        ),
    ]

