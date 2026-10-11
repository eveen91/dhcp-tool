from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class DomainMigrationTests(TransactionTestCase):
    def test_upgrade_preserves_existing_firewall_and_initializes_its_draft(self):
        old = [("dhcp_tool", "0001_initial")]
        target = [("dhcp_tool", "0002_version_firewall_description_firewall_location_and_more")]
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        try:
            apps = executor.loader.project_state(old).apps
            fw = apps.get_model("dhcp_tool", "Firewall").objects.create(
                name="fw-existing", profile="R82.10", archived=True
            )
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            restored = apps.get_model("dhcp_tool", "Firewall").objects.get(pk=fw.pk)
            self.assertEqual(restored.name, "fw-existing")
            self.assertTrue(restored.archived)
            draft = apps.get_model("dhcp_tool", "Draft").objects.filter(firewall_id=fw.pk).first()
            self.assertIsNotNone(draft)
            self.assertEqual(draft.revision, 1)
            self.assertEqual(draft.settings, {})
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
