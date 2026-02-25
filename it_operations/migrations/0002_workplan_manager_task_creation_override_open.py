from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('it_operations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='workplan',
            name='manager_task_creation_override_open',
            field=models.BooleanField(
                default=False,
                help_text='Manager override to reopen task creation after deadline for the current week only.',
            ),
        ),
    ]
