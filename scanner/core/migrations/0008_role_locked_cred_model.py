from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_roadmap_features"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="role_locked",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="credentialprofile",
            name="model",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
