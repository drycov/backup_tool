from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="LdapConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=False)),
                ("directory_type", models.CharField(default="ldap", max_length=16)),
                ("server", models.CharField(blank=True, default="", max_length=512)),
                ("use_ssl", models.BooleanField(default=False)),
                ("start_tls", models.BooleanField(default=True)),
                ("bind_dn", models.CharField(blank=True, default="", max_length=512)),
                ("bind_password", models.CharField(blank=True, default="", max_length=512)),
                ("user_base", models.CharField(blank=True, default="", max_length=512)),
                ("user_filter", models.CharField(default="(uid={username})", max_length=256)),
                ("user_dn_template", models.CharField(blank=True, default="", max_length=512)),
                ("user_upn_suffix", models.CharField(blank=True, default="", max_length=256)),
                ("admin_groups", models.TextField(blank=True, default="")),
                ("operator_groups", models.TextField(blank=True, default="")),
                ("default_role", models.CharField(default="viewer", max_length=32)),
                ("fallback_local", models.BooleanField(default=True)),
                ("connect_timeout", models.PositiveIntegerField(default=10)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "ldap_config"},
        ),
    ]
