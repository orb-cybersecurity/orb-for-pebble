package io.rebble.libpebblecommon.js

/** Synchronous JS instance IDs let the asynchronous, origin-checked page bridge carry sockets. */
fun configPageWebSocketJs(): String = """
(function (global) {
  var next = 0;
  var documentId = String(Date.now()) + ':' + String(Math.random());
  global.__orbSocketDocument = documentId;
  function dispatch(method, args) {
    if (!global.__pebbleConfig) throw new DOMException('No config network bridge', 'SecurityError');
    global.__pebbleConfig.socket({ document: documentId, method: method, args: args }).then(function (answer) {
      if (answer && answer.error && method === 'createInstance') {
        var socket = global.WebSocket._instances.get(args[3]);
        if (socket) { socket._onError(); socket._onClose(1006, '', false); }
      }
    });
  }
  global._WebSocketManager = {
    createInstance: function (url, protocols, headers) {
      var target = new URL(url, global.location.href);
      if (target.protocol === 'https:') target.protocol = 'wss:';
      if (target.protocol === 'http:') target.protocol = 'ws:';
      if ((target.protocol !== 'ws:' && target.protocol !== 'wss:') || target.hash) {
        throw new SyntaxError('Invalid WebSocket URL');
      }
      var id = ++next;
      dispatch('createInstance', [target.href, protocols, headers, id]);
      return id;
    },
    send: function (id, data, binary) { dispatch('send', [id, data, binary]); },
    close: function (id, code, reason) { dispatch('close', [id, code, reason]); },
  };
})(globalThis);
""" + WEBSOCKET_JS + "WebSocket._defaultBinaryType = 'blob';"
