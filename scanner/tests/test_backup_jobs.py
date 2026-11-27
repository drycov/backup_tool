from unittest.mock import patch
from django.test import TestCase

from core.models import BackgroundTask, Device, User
from services.backup_jobs import create_job, execute, list_jobs


class BackupJobsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="backup-admin", role="admin")
        self.device = Device.objects.create(name="test-router",ip="192.0.2.1",model="routeros")
    def test_job_and_duplicate(self):
        with patch("services.task_queue.is_database_available",return_value=True):
            job = create_job(self.user,self.device.name,"config")
            self.assertEqual(job.status, BackgroundTask.STATUS_PENDING)
            with self.assertRaises(ValueError):
                create_job(self.user,self.device.name,"mikrotik")
        self.assertEqual(list_jobs(self.user,self.device.name)[0]["id"],job.pk)
    def test_worker_rechecks_permissions(self):
        self.user.is_active=False
        self.user.save()
        with self.assertRaises(PermissionError):
            execute({"user_id":self.user.pk,"device_id":self.device.pk,"device":self.device.name,"kind":"config"})

    def test_cancel_pending(self):
        from services.backup_jobs import cancel_job, query_jobs
        with patch("services.task_queue.is_database_available",return_value=True):
            job=create_job(self.user,self.device.name,"config")
        cancel_job(self.user,job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status,"cancelled")
        self.assertEqual(query_jobs(self.user,status="cancelled")["items"][0]["id"],job.pk)
        with self.assertRaises(ValueError):
            cancel_job(self.user,job.pk)

    def test_engine_history(self):
        from services.backup_jobs import query_jobs, record_engine_finish, record_engine_start

        job_id = record_engine_start(self.device.name)
        record_engine_finish(job_id, "partial")
        result = query_jobs(self.user, source="automatic")
        self.assertEqual(result["items"][0]["status"], "failed")
        self.assertEqual(result["items"][0]["source"], "automatic")

    def test_device_lock(self):
        from services.backup_lock import BackupBusy, backup_lock

        with backup_lock(self.device.name):
            with self.assertRaises(BackupBusy):
                with backup_lock(self.device.name):
                    pass

    def test_scope_filters_numeric_device_ids(self):
        from services.backup_jobs import query_jobs, record_engine_start

        other = Device.objects.create(name="other", ip="192.0.2.2", group="other")
        record_engine_start(self.device.name)
        record_engine_start(other.name)
        viewer = User.objects.create(username="scoped", role="viewer", allowed_groups=["default"])
        result = query_jobs(viewer)
        self.assertEqual([j["device"] for j in result["items"]], [self.device.name])
