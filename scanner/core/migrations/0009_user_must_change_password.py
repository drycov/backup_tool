from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_role_locked_cred_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="must_change_password",
            field=models.BooleanField(default=False),
        ),
    ]
