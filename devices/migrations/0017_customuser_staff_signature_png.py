from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0016_deviceagreement_uploaded_uaf_pdf"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="staff_signature_png",
            field=models.TextField(
                blank=True,
                help_text="Optional saved IT signature (base64 PNG data URL)",
                null=True,
            ),
        ),
    ]

