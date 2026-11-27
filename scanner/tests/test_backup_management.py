from datetime import datetime, timezone
from unittest.mock import patch

from django.test import SimpleTestCase

from services.change_detection import classify_patch
from services.group_policies import GroupPolicyData, _nullable_bool
from services.maintenance_window import is_maintenance_window_active
from services.policy_engine import resolve_policy


class BackupManagementTests(SimpleTestCase):
    def test_policy_override_false(self):
        group = GroupPolicyData("core", 120, "", False, None, None, None, None, 12)
        with patch("services.policy_engine.get_policy", return_value=group):
            result = resolve_policy("core", 3600)
        self.assertEqual(result["interval_sec"], 120)
        self.assertFalse(result["binary_enabled"])
        self.assertTrue(result["export_enabled"])
        self.assertEqual(result["sources"]["binary_enabled"], "group")
        self.assertFalse(_nullable_bool("false"))

    def test_firewall_risk(self):
        result = classify_patch("@@ -1,2 +1,2 @@\n /ip firewall filter\n- action=drop\n+ action=accept")
        self.assertEqual(result["severity"], "critical")
        self.assertIn("firewall", result["categories"])
        self.assertEqual(result["added"], 1)

    def test_overnight_window_uses_start_day(self):
        self.assertTrue(is_maintenance_window_active(
            now=datetime(2026, 11, 28, 3, tzinfo=timezone.utc), days=[4]))
