"""Offline checks of release identity guards and stored source preservation."""
import os
import re
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


class SourcePreservationTest(unittest.TestCase):
    def test_source_initializer_does_not_rewrite_http_ownership_urls(self):
        dao = ROOT / 'mobileapp/util/src/commonMain/kotlin/coredevices/database/AppstoreSource.kt'
        initializer = ROOT / 'mobileapp/pebble/src/commonMain/kotlin/coredevices/pebble/services/AppstoreSources.kt'
        self.assertNotIn('upgradeHttpSources', dao.read_text() + initializer.read_text())
        self.assertNotRegex(dao.read_text(), r'UPDATE AppstoreSource SET url')
        web = ROOT / 'mobileapp/pebble/src/commonMain/kotlin/coredevices/pebble/services/PebbleWebServices.kt'
        self.assertIn('.filter { validSourceUrl(it.url) }', web.read_text())


class BuildCommitTest(unittest.TestCase):
    def test_missing_or_different_build_commit_is_refused_before_network(self):
        script = (ROOT / 'tools/github_release.sh').read_text()
        guard = next(line for line in script.splitlines() if 'field commit' in line)
        self.assertLess(script.index(guard), script.index('gh auth status'))
        self.assertIn('echo "commit: $(git rev-parse HEAD)"', (ROOT / 'tools/release_build.sh').read_text())
        for built, expected in [('', 1), ('old', 1), ('tag-commit', 0)]:
            with self.subTest(built=built):
                harness = 'field() { printf "%s" "$BUILT"; }; die() { echo "$*" >&2; exit 1; }; COMMIT=tag-commit; APK=test.apk\n'
                result = subprocess.run(['bash', '-c', harness + guard], env={**os.environ, 'BUILT': built},
                                        capture_output=True, text=True)
                self.assertEqual(expected, result.returncode)
                if expected: self.assertIn('built from another commit', result.stderr)


if __name__ == '__main__':
    unittest.main()
