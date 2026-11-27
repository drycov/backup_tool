from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0029_backup_management")]
    operations = [
        migrations.CreateModel(
            name="BackupArtifact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(max_length=8)),
                ("filename", models.CharField(max_length=255)),
                ("sha256", models.CharField(max_length=64)),
                ("size_bytes", models.PositiveBigIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("remote_key", models.CharField(blank=True, default="", max_length=512)),
                ("remote_status", models.CharField(default="disabled", max_length=16)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.device")),
            ],
            options={"db_table": "backup_artifacts"},
        ),
        migrations.AddConstraint(model_name="backupartifact", constraint=models.UniqueConstraint(fields=["device", "kind", "filename"], name="backup_artifact_identity")),
    ]
