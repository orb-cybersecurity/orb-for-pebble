#!/usr/bin/env python3
"""Execute the shipped WebView shims with an in-memory native transport; no sockets are used."""
import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "mobileapp"
JS = APP / "libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js"


def script(path):
    return re.search(r'"""(.*?)"""', path.read_text(), re.S)[1].replace("${'$'}", "$")


XHR_HOST = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
let next = 0, permitted = true, calls = [], aborts = 0, pending = new Map();
globalThis.fetch = () => { throw Error('native fetch escaped'); };
globalThis._XMLHTTPRequestManager = {
  getXHRInstanceID() { const id = ++next; pending.set(id, { headers: {} }); return id; },
  open(id, method, url) { Object.assign(pending.get(id), { method, url }); },
  setRequestHeader(id, name, value) { pending.get(id).headers[name.toLowerCase()] = value; },
  abort(id) {
    aborts++;
    const xhr = XMLHttpRequest._instances.get(id);
    if (xhr) { xhr.readyState = 4; xhr._dispatchEvent('abort', {}); }
    pending.delete(id);
  },
  send(id, type, data, binary) {
    const call = pending.get(id);
    call.body = data === null ? null : binary ? Buffer.from(data, 'base64') : data;
    calls.push(call);
    queueMicrotask(() => {
      const xhr = XMLHttpRequest._instances.get(id);
      if (!xhr) return;
      if (!permitted) {
        xhr._notAllowed = true; xhr.readyState = 4; xhr._dispatchEvent('error', {}); return;
      }
      const status = call.url.includes('/missing') ? 404 : call.method === 'HEAD' ? 204 : 200;
      xhr._onResponseComplete({ 'content-type': 'application/json', 'x-result': 'checked' },
        status, 'OK', Buffer.from('{"city":"Tromsø"}').toString('base64'));
      xhr.readyState = 4;
      xhr._dispatchEvent('load', {}); xhr._dispatchEvent('loadend', {});
    });
  },
};
"""


class WebNetworkTests(unittest.TestCase):
    def node(self, source):
        result = subprocess.run(["node", "-"], input=source, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def fetch(self, test):
        xhr = script(JS / "XmlHttpRequestJs.kt")
        fetch = script(APP / "libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/PkjsFetchJs.kt")
        self.node(XHR_HOST + "\nvm.runInThisContext(" + json.dumps("{" + xhr + "}") + ");\n" +
                  "vm.runInThisContext(" + json.dumps(fetch) + ");\n" +
                  "(async () => {\n" + test + "\n})().catch(e => { console.error(e); process.exitCode = 1; });")

    def test_allowed_fetch_uses_xhr_without_cors_and_preserves_request_response_and_bytes(self):
        self.fetch(r"""
const request = new Request('https://api.example/weather', {
  method: 'POST', headers: { 'content-type': 'application/json', authorization: 'Bearer test' },
  body: JSON.stringify({ city: 'Tromsø' }),
});
const response = await fetch(request);
assert.equal(calls.length, 1);
assert.equal(calls[0].method, 'POST');
assert.equal(calls[0].url, request.url);
assert.equal(calls[0].headers.authorization, 'Bearer test');
assert.deepEqual(JSON.parse(calls[0].body.toString('utf8')), { city: 'Tromsø' });
assert.equal(response.headers.get('x-result'), 'checked');
assert.equal(response.url, request.url);
assert.equal(response.ok, true);
assert.deepEqual(await response.clone().json(), { city: 'Tromsø' });
assert.equal(new TextDecoder().decode(await response.arrayBuffer()), '{"city":"Tromsø"}');
const bytes = new Uint8Array([0, 128, 255]);
await fetch('https://api.example/binary', { method: 'POST', body: bytes });
assert.deepEqual([...calls[1].body], [...bytes]);
const missing = await fetch('https://api.example/missing');
assert.equal(missing.status, 404); assert.equal(missing.ok, false);
const head = await fetch('https://api.example/head', { method: 'HEAD' });
assert.equal(await head.text(), '');
""")

    def test_revocation_rejects_fetch_and_xhr_uses_the_same_transport(self):
        self.fetch(r"""
await fetch('https://api.example/allowed');
permitted = false;
await assert.rejects(fetch('https://api.example/revoked'), TypeError);
const xhr = new XMLHttpRequest();
xhr.open('GET', 'https://api.example/revoked');
const refused = new Promise(resolve => { xhr.onerror = resolve; });
xhr.send(null); await refused;
assert.equal(xhr._notAllowed, true);
assert.equal(calls.length, 3);
""")

    def test_abort_and_unsupported_redirect_modes_never_fall_back_to_native_fetch(self):
        self.fetch(r"""
const controller = new AbortController(); controller.abort();
await assert.rejects(fetch('https://api.example/data', { signal: controller.signal }), { name: 'AbortError' });
assert.equal(calls.length, 0); assert.equal(aborts, 1);
await assert.rejects(fetch('https://api.example/data', { redirect: 'manual' }), TypeError);
await assert.rejects(fetch('https://api.example/data', { redirect: 'error' }), TypeError);
assert.equal(calls.length, 0);
""")

    def test_config_socket_adapter_uses_message_bridge_and_preserves_relative_urls_and_events(self):
        adapter = script(JS / "ConfigPageWebSocketJs.kt") + script(JS / "WebSocketJs.kt")
        self.node(r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const commands = [];
globalThis.location = { href: 'https://config.example/settings' };
globalThis.__pebbleConfig = { socket(command) {
  commands.push(command); return Promise.resolve(null);
} };
""" + "vm.runInThisContext(" + json.dumps(adapter) + ");\n" + r"""
const ws = new WebSocket('/socket', ['chat']);
assert.equal(commands.length, 1);
assert.equal(commands[0].method, 'createInstance');
assert.equal(commands[0].args[0], 'wss://config.example/socket');
assert.equal(commands[0].args[1], 'chat');
assert.equal(commands[0].document, __orbSocketDocument);
assert.equal(WebSocket._instances.get(commands[0].args[3]), ws);
let message;
ws.onmessage = event => { message = event.data; };
ws._onOpen('chat'); ws.send('hello'); ws._onMessage('reply', false);
assert.equal(message, 'reply');
assert.equal(commands[1].method, 'send');
ws.close(); assert.equal(commands[2].method, 'close');
delete globalThis.__pebbleConfig;
assert.throws(() => new WebSocket('wss://api.example/socket'), { name: 'SecurityError' });
""")


if __name__ == "__main__":
    unittest.main()
