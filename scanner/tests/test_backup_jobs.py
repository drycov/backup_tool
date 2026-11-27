from unittest.mock import patch
from django.test import TestCase
from core.models import Device, User, BackgroundTask
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
