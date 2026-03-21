import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import 'api_client.dart';

/// WebSocket message types (server -> client)
class WsMessageType {
  static const aiReply = 'ai_reply';
  static const proactiveDm = 'proactive_dm';
  static const messageSaved = 'message_saved';
  static const pong = 'pong';
  static const error = 'error';
}

/// Connection status for UI display
enum WsConnectionStatus {
  disconnected,
  connecting,
  connected,
  reconnecting,
}

/// WebSocket client for real-time chat with reconnection and heartbeat.
class WsClient {
  final int aiId;
  final void Function(WsConnectionStatus status)? onStatusChange;

  WebSocketChannel? _channel;
  StreamSubscription? _subscription;

  final _messageController = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get messages => _messageController.stream;

  WsConnectionStatus _status = WsConnectionStatus.disconnected;
  WsConnectionStatus get status => _status;

  Timer? _heartbeatTimer;
  Timer? _pongTimeoutTimer;
  Timer? _reconnectTimer;

  int _reconnectAttempts = 0;
  static const _maxReconnectAttempts = 10;
  static const _heartbeatInterval = Duration(seconds: 30);
  static const _pongTimeout = Duration(seconds: 10);

  bool _disposed = false;
  bool _intentionalDisconnect = false;

  WsClient({required this.aiId, this.onStatusChange});

  /// Connect to the WebSocket server
  Future<void> connect() async {
    if (_disposed) return;
    if (_status == WsConnectionStatus.connecting) return;

    _intentionalDisconnect = false;
    _setStatus(WsConnectionStatus.connecting);

    final token = ApiClient.token;
    if (token == null) {
      _setStatus(WsConnectionStatus.disconnected);
      _messageController.add({
        'type': WsMessageType.error,
        'data': {'code': 'no_token', 'detail': 'Not authenticated'},
      });
      return;
    }

    final wsUrl = '${ApiClient.wsBaseUrl}/api/chat/ws/$aiId?token=$token';

    try {
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
      await _channel!.ready;

      _setStatus(WsConnectionStatus.connected);
      _reconnectAttempts = 0;
      _startHeartbeat();

      _subscription = _channel!.stream.listen(
        _onMessage,
        onError: _onError,
        onDone: _onDone,
        cancelOnError: false,
      );
    } catch (e) {
      _setStatus(WsConnectionStatus.disconnected);
      _scheduleReconnect();
    }
  }

  /// Send a chat message
  void sendMessage(String text, {String? postContext}) {
    _send({
      'type': 'message',
      'data': {
        'text': text,
        if (postContext != null) 'post_context': postContext,
      },
    });
  }

  /// Send a ping (usually handled automatically by heartbeat)
  void sendPing() {
    _send({'type': 'ping'});
  }

  /// Disconnect intentionally (no reconnect)
  void disconnect() {
    _intentionalDisconnect = true;
    _dispose();
  }

  /// Clean up resources
  void dispose() {
    _disposed = true;
    _dispose();
    _messageController.close();
  }

  void _send(Map<String, dynamic> message) {
    if (_channel == null || _status != WsConnectionStatus.connected) {
      // Queue message or show error
      _messageController.add({
        'type': WsMessageType.error,
        'data': {'code': 'not_connected', 'detail': 'WebSocket not connected'},
      });
      return;
    }
    _channel!.sink.add(jsonEncode(message));
  }

  void _onMessage(dynamic message) {
    _cancelPongTimeout();

    try {
      final data = jsonDecode(message as String) as Map<String, dynamic>;
      final type = data['type'] as String?;

      if (type == 'pong') {
        // Heartbeat response, no action needed
        return;
      }

      _messageController.add(data);
    } catch (e) {
      _messageController.add({
        'type': WsMessageType.error,
        'data': {'code': 'parse_error', 'detail': 'Failed to parse message'},
      });
    }
  }

  void _onError(dynamic error) {
    _setStatus(WsConnectionStatus.disconnected);
    _stopHeartbeat();
    _scheduleReconnect();
  }

  void _onDone() {
    _setStatus(WsConnectionStatus.disconnected);
    _stopHeartbeat();
    if (!_intentionalDisconnect && !_disposed) {
      _scheduleReconnect();
    }
  }

  void _setStatus(WsConnectionStatus newStatus) {
    if (_status != newStatus) {
      _status = newStatus;
      onStatusChange?.call(newStatus);
    }
  }

  void _startHeartbeat() {
    _stopHeartbeat();
    _heartbeatTimer = Timer.periodic(_heartbeatInterval, (_) {
      if (_status == WsConnectionStatus.connected) {
        sendPing();
        _startPongTimeout();
      }
    });
  }

  void _stopHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _cancelPongTimeout();
  }

  void _startPongTimeout() {
    _cancelPongTimeout();
    _pongTimeoutTimer = Timer(_pongTimeout, () {
      // Pong not received, connection likely dead
      _channel?.sink.close();
      _setStatus(WsConnectionStatus.disconnected);
      _scheduleReconnect();
    });
  }

  void _cancelPongTimeout() {
    _pongTimeoutTimer?.cancel();
    _pongTimeoutTimer = null;
  }

  void _scheduleReconnect() {
    if (_disposed || _intentionalDisconnect) return;
    if (_reconnectAttempts >= _maxReconnectAttempts) {
      _messageController.add({
        'type': WsMessageType.error,
        'data': {
          'code': 'max_reconnect',
          'detail': 'Max reconnection attempts reached',
        },
      });
      return;
    }

    _reconnectTimer?.cancel();

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s max
    final delay = Duration(
      seconds: _clamp(1 << _reconnectAttempts, 1, 30),
    );
    _reconnectAttempts++;

    _setStatus(WsConnectionStatus.reconnecting);

    _reconnectTimer = Timer(delay, () {
      if (!_disposed && !_intentionalDisconnect) {
        connect();
      }
    });
  }

  void _dispose() {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _stopHeartbeat();
    _subscription?.cancel();
    _subscription = null;
    _channel?.sink.close();
    _channel = null;
    _setStatus(WsConnectionStatus.disconnected);
  }

  int _clamp(int value, int min, int max) {
    if (value < min) return min;
    if (value > max) return max;
    return value;
  }
}
