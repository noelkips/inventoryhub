from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0004_auto_20260119_1320'),
    ]

    operations = [
        migrations.AlterField(
            model_name='deviceagreement',
            name='issuance_it_user',
            field=models.ForeignKey(
                on_delete=models.SET_NULL,
                null=True,
                related_name='issuance_agreements',
                to='devices.CustomUser'
            ),
        ),
        migrations.AlterField(
            model_name='deviceagreement',
            name='clearance_it_user',
            field=models.ForeignKey(
                on_delete=models.SET_NULL,
                null=True,
                related_name='clearance_agreements',
                to='devices.CustomUser'
            ),
        ),
    ]
