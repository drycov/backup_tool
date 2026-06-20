from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_provision_bulk_log"),
    ]

    operations = [
        migrations.AddField(
            model_name="integrationconfig",
            name="zabbix_api_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="zabbix_api_token",
            field=models.CharField(blank=True, default="", max_length=256),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="zabbix_api_url",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
    ]
