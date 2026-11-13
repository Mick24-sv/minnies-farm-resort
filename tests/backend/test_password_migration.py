import contextlib
import io
import unittest
from unittest.mock import Mock, patch

from scripts.migrate_legacy_passwords import is_legacy_plaintext, main


class PasswordMigrationTest(unittest.TestCase):
    def test_existing_hash_formats_are_not_candidates(self):
        for value in [None, '', '$pbkdf2-sha256$hash', '$2b$hash', '$argon2id$hash',
                      'pbkdf2:sha256:hash', 'scrypt:hash', 'f' * 64]:
            self.assertFalse(is_legacy_plaintext(value))
        self.assertTrue(is_legacy_plaintext('example-legacy-value'))

    @patch('scripts.migrate_legacy_passwords.requests.patch')
    @patch('scripts.migrate_legacy_passwords.requests.get')
    @patch.dict('os.environ', {'SUPABASE_URL': 'https://example.invalid', 'SUPABASE_KEY': 'dummy-key'})
    def test_default_dry_run_never_updates_accounts(self, get, update):
        get.return_value = Mock(ok=True, json=lambda: [{'id': 1, 'role': 'staff', 'password': 'example-legacy-value'}])
        with patch('sys.argv', ['migration']), contextlib.redirect_stdout(io.StringIO()):
            main()
        update.assert_not_called()

    @patch('scripts.migrate_legacy_passwords.requests.patch')
    @patch('scripts.migrate_legacy_passwords.requests.get')
    @patch.dict('os.environ', {'SUPABASE_URL': 'https://example.invalid', 'SUPABASE_KEY': 'dummy-key'})
    def test_reapplying_with_no_legacy_accounts_does_not_write(self, get, update):
        get.return_value = Mock(ok=True, json=lambda: [])
        with patch('sys.argv', ['migration', '--apply']), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            main()
        update.assert_not_called()


if __name__ == '__main__':
    unittest.main()
