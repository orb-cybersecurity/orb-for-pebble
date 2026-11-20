#!/usr/bin/env python3
"""Load shipped PKJS assets in Chromium with an isolated, disconnected network namespace."""
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ASSETS = Path(__file__).resolve().parents[1] / 'mobileapp/libpebble3/src/androidMain/assets'
NATIVE = r'''
window.Pebble = {};
const violations = [];
document.addEventListener('securitypolicyviolation', e => violations.push(e.violatedDirective));
window._Pebble = new Proxy({
  startupScriptHasLoaded: async () => {
    const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=';
    const decode = src => new Promise(resolve => { const i = new Image(); i.onload = () => resolve(true); i.onerror = () => resolve(false); i.src = src; });
    const dataImage = await decode(image);
    const bytes = Uint8Array.from(atob(image.split(',')[1]), x => x.charCodeAt(0));
    const blobImage = await decode(URL.createObjectURL(new Blob([bytes], {type: 'image/png'})));
    document.body.dataset.runtime = JSON.stringify({
      guard: typeof __pebbleGuardRealms === 'function', pebble: typeof Pebble.addEventListener === 'function',
      ready: typeof signalReady === 'function', messages: typeof signalNewAppMessageData === 'function',
      config: typeof signalShowConfiguration === 'function', rtc: typeof RTCPeerConnection,
      dataImage, blobImage, violations });
  }
}, {get: (o,k) => k in o ? o[k] : () => null});
'''


class PkjsRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.browser = shutil.which('chromium-browser') or shutil.which('chromium')
        if not cls.browser or not shutil.which('unshare'):
            raise unittest.SkipTest('Chromium and unshare are required for the offline runtime probe')
        probe = subprocess.run(['unshare', '--user', '--map-root-user', '--net', 'true'], capture_output=True)
        if probe.returncode:
            raise unittest.SkipTest('Network namespace isolation is unavailable')

    def load(self, invalid_source=False):
        with tempfile.TemporaryDirectory(prefix='orb-csp-') as directory:
            work = Path(directory)
            for asset in ('startup.js', 'realm_guard.js'):
                shutil.copyfile(ASSETS / asset, work / asset)
            (work / 'native.js').write_text(NATIVE)
            page = (ASSETS / 'webview_startup.html').read_text()
            if invalid_source:
                page = page.replace('script-src file:', 'script-src file:///android_asset/')
            # Only resource URLs move; the production CSP is tested unchanged.
            page = page.replace('src="file:///android_asset/', 'src="' + work.as_uri() + '/')
            page = page.replace('    <script type=', f'    <script src="{(work / "native.js").as_uri()}"></script>\n    <script type=', 1)
            (work / 'test.html').write_text(page)
            result = subprocess.run(['unshare', '--user', '--map-root-user', '--net', self.browser,
                '--headless', '--no-sandbox', '--disable-gpu', '--disable-background-networking',
                '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check',
                '--enable-logging=stderr', f'--user-data-dir={work / "profile"}',
                '--virtual-time-budget=3000', '--dump-dom', (work / 'test.html').as_uri()],
                env={**os.environ, 'XDG_CONFIG_HOME': str(work / 'config'),
                     'XDG_CACHE_HOME': str(work / 'cache'), 'XDG_DATA_HOME': str(work / 'data')},
                text=True, capture_output=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            return result

    def test_shipped_scripts_initialize_and_checked_images_decode(self):
        result = self.load()
        match = re.search(r'data-runtime="([^"]+)"', result.stdout)
        self.assertIsNotNone(match, result.stdout + result.stderr)
        self.assertEqual(dict(guard=True, pebble=True, ready=True, messages=True, config=True,
                              rtc='undefined', dataImage=True, blobImage=True, violations=[]),
                         json.loads(html.unescape(match[1])))
        self.assertNotIn('invalid source', result.stderr)

    def test_empty_host_source_reproduces_startup_failure(self):
        result = self.load(invalid_source=True)
        self.assertNotIn('data-runtime=', result.stdout)
        self.assertIn('invalid source', result.stderr)


if __name__ == '__main__':
    unittest.main()
