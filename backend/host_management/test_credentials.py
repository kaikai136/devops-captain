from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from .import_export import export_host_management_payload, import_credentials
from .models import HostCredential


class UnifiedCredentialBackupTests(TestCase):
    def test_old_backup_type_is_ignored_and_new_backup_omits_it(self):
        import_credentials([{
            "name": "previous-app", "credentialType": "application", "username": "ops",
            "password": "password", "privateKeyName": "id_ed25519", "privateKey": "key", "remark": "keep",
        }], {"credentials": 0})
        account = HostCredential.objects.get()
        self.assertEqual(account.username, "ops")
        self.assertEqual(account.password, "password")
        exported = export_host_management_payload()["credentials"][0]
        self.assertNotIn("credentialType", exported)
        self.assertEqual(exported["privateKey"], "key")
        self.assertEqual(exported["remark"], "keep")


class UnifiedCredentialMigrationTests(TransactionTestCase):
    def test_removing_type_preserves_both_kinds_and_all_credential_content(self):
        old_target = [("host_management", "0013_hostcredential_username_optional")]
        target = [("host_management", "0014_remove_hostcredential_credential_type")]
        executor = MigrationExecutor(connection)
        executor.migrate(old_target)
        try:
            OldCredential = executor.loader.project_state(old_target).apps.get_model("host_management", "HostCredential")
            for kind in ("host", "application"):
                OldCredential.objects.create(name=kind, credential_type=kind, username="ops", password="secret", port=2222,
                                             private_key_name="id_key", private_key="key", remark="keep")
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(target)
        self.assertEqual(HostCredential.objects.count(), 2)
        for account in HostCredential.objects.all():
            self.assertEqual((account.username, account.password, account.port, account.private_key_name, account.private_key, account.remark),
                             ("ops", "secret", 2222, "id_key", "key", "keep"))
        self.assertNotIn("credential_type", {field.name for field in HostCredential._meta.fields})
