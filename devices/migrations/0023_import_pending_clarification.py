from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0022_devicedeletionrequest"),
    ]

    operations = [
        migrations.AddField(
            model_name="import",
            name="pending_clarification",
            field=models.BooleanField(default=False),
        ),
    ]
