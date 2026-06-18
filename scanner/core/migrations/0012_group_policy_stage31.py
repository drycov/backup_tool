from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_stage3_foundation"),
    ]

    operations = [
        migrations.AddField(
            model_name="grouppolicy",
            name="compliance_sla_hours",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="grouppolicy",
            name="maintenance_override",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="grouppolicy",
            name="notify_email",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="grouppolicy",
            name="notify_telegram",
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
