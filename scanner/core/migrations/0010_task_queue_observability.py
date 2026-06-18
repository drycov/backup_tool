from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_user_must_change_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanconfig",
            name="schedule_discover",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="scanconfig",
            name="schedule_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="scanconfig",
            name="schedule_interval_hours",
            field=models.PositiveIntegerField(default=24),
        ),
        migrations.AddField(
            model_name="scanconfig",
            name="schedule_last_run_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="BackgroundTask",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("task_type", models.CharField(db_index=True, max_length=64)),
                (
                    "status",
                    models.CharField(db_index=True, default="pending", max_length=16),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "correlation_id",
                    models.CharField(blank=True, db_index=True, default="", max_length=64),
                ),
                ("scheduled_at", models.DateTimeField(db_index=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=3)),
                ("last_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "background_tasks",
                "ordering": ["scheduled_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["status", "scheduled_at"],
                        name="background__status_6a0f0d_idx",
                    ),
                    models.Index(
                        fields=["task_type", "status"],
                        name="background__task_ty_8e2c1a_idx",
                    ),
                ],
            },
        ),
    ]
