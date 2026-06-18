from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_provision_bulk_run"),
    ]

    operations = [
        migrations.AddField(
            model_name="network",
            name="site",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="network",
            name="role",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
    ]
