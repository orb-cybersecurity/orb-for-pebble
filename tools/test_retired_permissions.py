"""Offline checks of the bulk permission cleanup and runtime key handling."""
from pathlib import Path
import re
import sqlite3
import unittest

MAIN = Path(__file__).resolve().parents[1] / 'mobileapp/libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon'


class RetiredPermissionsTest(unittest.TestCase):
    def test_bulk_delete_preserves_other_permissions_for_every_app(self):
        source = (MAIN / 'database/dao/LockerAppPermissionDao.kt').read_text()
        query = re.search(r'@Query\("([^"\n]+)"\)\s+suspend fun deleteRetiredPermissions\(\)', source)[1]
        keys = ['LegacyPebbleKit', 'LegacyPebbleKit/', 'LegacyPebbleKit/old',
                'LegacyPebbleKitExtra', 'Calendar', 'PebbleKit2/com.example',
                '00000000-0000-0000-0000-00000000a001:LegacyPebbleKit']
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE AppPermission(appUuid TEXT, permission TEXT, granted INTEGER, lastUsedAtMs INTEGER)')
            rows = [(app, key, granted, 42) for app in ['uncached', 'unchanged', 'sideloaded']
                    for key in keys for granted in [None, 0, 1]]
            db.executemany('INSERT INTO AppPermission VALUES (?, ?, ?, ?)', rows)
            db.execute(query)
            expected = [row for row in rows if row[1] in keys[3:]]
            self.assertEqual(expected, db.execute('SELECT * FROM AppPermission').fetchall())
            db.execute(query)
            self.assertEqual(expected, db.execute('SELECT * FROM AppPermission').fetchall())

    def test_runtime_decisions_do_not_check_the_retired_name(self):
        permissions = (MAIN / 'permissions/AppPermissions.kt').read_text()
        self.assertNotIn('isRemovedPermission', permissions)
        self.assertNotIn('LegacyPebbleKit', permissions)
        self.assertNotIn('recordDenied', permissions)


if __name__ == '__main__':
    unittest.main()
