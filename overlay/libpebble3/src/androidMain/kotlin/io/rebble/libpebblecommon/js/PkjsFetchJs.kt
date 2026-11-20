package io.rebble.libpebblecommon.js

/** Browser-compatible bodies and responses, transported by the checked native XHR manager. */
internal const val PKJS_FETCH_JS = """
(function (global) {
  'use strict';
  var XHR = global.XMLHttpRequest;
  var Request = global.Request, Response = global.Response, Headers = global.Headers;
  var Promise = global.Promise, DOMException = global.DOMException;
  Object.defineProperty(global, 'fetch', {
    configurable: false, writable: false,
    value: function (input, init) {
      return new Promise(function (resolve, reject) {
        var request;
        try { request = new Request(input, init); } catch (e) { reject(e); return; }
        // The native manager follows redirects only after checking each destination.
        if (request.redirect !== 'follow') {
          reject(new TypeError('Only checked redirect following is supported')); return;
        }
        var xhr = new XHR(), signal = request.signal, finished = false;
        function finish(callback, value) {
          if (finished) return;
          finished = true;
          signal.removeEventListener('abort', abort);
          callback(value);
        }
        function abort() {
          finish(reject, new DOMException('The request was aborted', 'AbortError'));
          xhr.abort();
        }
        xhr.open(request.method, request.url, true);
        xhr.responseType = 'arraybuffer';
        request.headers.forEach(function (value, name) { xhr.setRequestHeader(name, value); });
        xhr.onload = function () {
          try {
            var headers = new Headers();
            xhr.getAllResponseHeaders().split(/\r?\n/).forEach(function (line) {
              var colon = line.indexOf(':');
              if (colon > 0) headers.append(line.slice(0, colon), line.slice(colon + 1).trim());
            });
            var empty = request.method === 'HEAD' || [204, 205, 304].indexOf(xhr.status) !== -1;
            var response = new Response(empty ? null : xhr.response, {
              status: xhr.status, statusText: xhr.statusText, headers: headers,
            });
            Object.defineProperty(response, 'url', { value: request.url });
            finish(resolve, response);
          } catch (e) { finish(reject, e); }
        };
        xhr.onerror = xhr.ontimeout = function () { finish(reject, new TypeError('Network request failed')); };
        xhr.onabort = function () { finish(reject, new DOMException('The request was aborted', 'AbortError')); };
        signal.addEventListener('abort', abort);
        if (signal.aborted) { abort(); return; }
        var body = request.method === 'GET' || request.method === 'HEAD'
          ? Promise.resolve(null) : request.arrayBuffer();
        body.then(function (bytes) {
          if (!finished) xhr.send(bytes);
        }, function (e) { finish(reject, e); xhr.abort(); });
      });
    },
  });
})(globalThis);
"""
