from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0027_scan_ai_analysis"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="ai_enrichment",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
