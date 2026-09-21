from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0026_radiusconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanrun",
            name="ai_analysis",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
