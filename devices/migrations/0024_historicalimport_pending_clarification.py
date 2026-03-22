from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0023_import_pending_clarification"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalimport",
            name="pending_clarification",
            field=models.BooleanField(default=False),
        ),
    ]
