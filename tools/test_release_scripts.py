"""Offline checks of release identity guards and the source-upgrade SQL."""
import os
import re
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMON = ROOT / 'tools/release_common.sh'


class ReleaseIdentityTest(unittest.TestCase):
    def certificate(self, output):
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory)
            tools = sdk / 'build-tools/1.0'
            tools.mkdir(parents=True)
            signer = tools / 'apksigner'
            signer.write_text('#!/bin/sh\ncat <<\'CERTIFICATE\'\n' + output + '\nCERTIFICATE\n')
            signer.chmod(0o700)
            return subprocess.run(['bash', '-c', 'source "$1"; orb_apk_certificate unused.apk',
                                   'test', str(COMMON)], env={**os.environ, 'ANDROID_HOME': str(sdk)},
                                  capture_output=True, text=True)

    def test_only_published_certificate_is_accepted(self):
        fingerprint = re.search(r'ORB_CERT_SHA256=([0-9a-f]+)', COMMON.read_text())[1]
        for value, expected in ((fingerprint, 0), (fingerprint.upper(), 0), ('0' * 64, 1), ('', 1)):
            with self.subTest(value=value):
                result = self.certificate('Signer #1 certificate SHA-256 digest: ' + value)
                self.assertEqual(expected, result.returncode, result.stderr)
        self.assertNotEqual(0, self.certificate(
            'Signer #1 certificate SHA-256 digest: ' + fingerprint + '\n'
            'Signer #2 certificate SHA-256 digest: ' + '0' * 64).returncode)

    def test_version_mismatch_stops_before_reading_apk_or_contacting_github(self):
        result = subprocess.run(['bash', str(ROOT / 'tools/github_release.sh'), '0.0.0-orb0'],
                                capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn('differs from version.properties', result.stderr)


class SourceUpgradeTest(unittest.TestCase):
    def test_upgrade_preserves_ids_and_settings_and_runs_once_per_http_row(self):
        source = ROOT / 'mobileapp/util/src/commonMain/kotlin/coredevices/database/AppstoreSource.kt'
        query = re.search(r'@Query\("(UPDATE AppstoreSource SET url = .*?)"\)', source.read_text())[1]
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE AppstoreSource(id INTEGER PRIMARY KEY, url TEXT, title TEXT, enabled INTEGER, algoliaApiKey TEXT)')
            rows = [(7, 'http://custom.example/api', 'custom', 0, None),
                    (8, 'https://secure.example/api', 'secure', 1, 'keep'),
                    (9, 'HTTP://old.example/api', 'old', 1, None)]
            db.executemany('INSERT INTO AppstoreSource VALUES (?, ?, ?, ?, ?)', rows)
            self.assertEqual(2, db.execute(query).rowcount)
            self.assertEqual([(7, 'https://custom.example/api', 'custom', 0, None), rows[1],
                              (9, 'https://old.example/api', 'old', 1, None)],
                             db.execute('SELECT * FROM AppstoreSource ORDER BY id').fetchall())
            self.assertEqual(0, db.execute(query).rowcount)


if __name__ == '__main__':
    unittest.main()
