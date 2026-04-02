// ============================================================================
// SoulPulse WebSocket 客户端
// ============================================================================
//
// 本文件提供与 SoulPulse 后端实时聊天功能的 WebSocket 连接管理，
// 包含：
// - WebSocket 连接建立与维护
// - 心跳机制（ping/pong）保持连接活跃
// - 自动重连机制（指数退避策略）
// - 消息发送与接收处理
// - 连接状态管理
//
// 主要类：
// - WsMessageType: WebSocket 消息类型常量定义
// - WsConnectionStatus: 连接状态枚举
// - WsClient: WebSocket 客户端核心类
//
// ============================================================================

import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import 'api_client.dart';

/// WebSocket 消息类型常量（服务器 -> 客户端）
///
/// 定义服务器发送给客户端的消息类型，用于消息分发处理
class WsMessageType {
  /// AI 回复消息类型
  static const aiReply = 'ai_reply';

  /// AI 主动发送消息类型（主动问候等）
  static const proactiveDm = 'proactive_dm';

  /// 消息保存确认类型
  static const messageSaved = 'message_saved';

  /// 心跳响应类型
  static const pong = 'pong';

  /// 错误消息类型
  static const error = 'error';
}

/// WebSocket 连接状态枚举
///
/// 用于 UI 显示连接状态指示器
enum WsConnectionStatus {
  /// 已断开连接
  disconnected,

  /// 正在连接
  connecting,

  /// 已连接
  connected,

  /// 正在重连
  reconnecting,
}

/// WebSocket 客户端
///
/// 提供实时聊天功能，支持：
/// - 自动连接与认证
/// - 心跳机制保持连接
/// - 自动重连（指数退避，最多 10 次）
/// - 消息发送与接收流
///
/// 使用示例：
/// ```dart
/// final ws = WsClient(aiId: 1, onStatusChange: (status) { ... });
/// ws.messages.listen((msg) { ... });  // 监听消息
/// ws.connect();                        // 建立连接
/// ws.sendMessage('Hello');             // 发送消息
/// ws.disconnect();                     // 断开连接
/// ```
class WsClient {
  /// 目标 AI 的 ID
  final int aiId;

  /// 连接状态变化回调函数
  ///
  /// 用于 UI 更新连接状态指示器
  final void Function(WsConnectionStatus status)? onStatusChange;

  /// WebSocket 通道对象
  WebSocketChannel? _channel;

  /// WebSocket 消息流订阅
  StreamSubscription? _subscription;

  /// 消息广播流控制器
  ///
  /// 将接收的消息广播给多个监听者
  final _messageController = StreamController<Map<String, dynamic>>.broadcast();

  /// 获取消息流，用于监听接收的消息
  Stream<Map<String, dynamic>> get messages => _messageController.stream;

  /// 当前连接状态
  WsConnectionStatus _status = WsConnectionStatus.disconnected;

  /// 获取当前连接状态
  WsConnectionStatus get status => _status;

  /// 心跳定时器（周期性发送 ping）
  Timer? _heartbeatTimer;

  /// pong 响应超时定时器
  Timer? _pongTimeoutTimer;

  /// 重连定时器
  Timer? _reconnectTimer;

  /// 重连尝试次数
  int _reconnectAttempts = 0;

  /// 最大重连尝试次数
  static const _maxReconnectAttempts = 10;

  /// 心跳间隔（30 秒）
  static const _heartbeatInterval = Duration(seconds: 30);

  /// pong 响应超时时间（10 秒）
  static const _pongTimeout = Duration(seconds: 10);

  /// 是否已释放资源
  bool _disposed = false;

  /// 是否为主动断开连接（不触发重连）
  bool _intentionalDisconnect = false;

  /// 构造函数
  ///
  /// [aiId] 目标 AI 的 ID
  /// [onStatusChange] 连接状态变化回调
  WsClient({required this.aiId, this.onStatusChange});

  /// 建立 WebSocket 连接
  ///
  /// 执行以下步骤：
  /// 1. 检查是否已释放或正在连接
  /// 2. 获取认证令牌并构造 WebSocket URL
  /// 3. 建立 WebSocket 连接
  /// 4. 启动心跳机制
  /// 5. 监听消息流
  Future<void> connect() async {
    // 如果已释放或正在连接，直接返回
    if (_disposed) return;
    if (_status == WsConnectionStatus.connecting) return;

    // 标记为非主动断开，允许重连
    _intentionalDisconnect = false;
    _setStatus(WsConnectionStatus.connecting);

    // 获取认证令牌，无令牌时发送错误消息
    final token = ApiClient.token;
    if (token == null) {
      _setStatus(WsConnectionStatus.disconnected);
      _messageController.add({
        'type': WsMessageType.error,
        'data': {'code': 'no_token', 'detail': 'Not authenticated'},
      });
      return;
    }

    // 构造 WebSocket URL，包含 AI ID 和认证令牌
    final wsUrl = '${ApiClient.wsBaseUrl}/api/chat/ws/$aiId?token=$token';

    try {
      // 建立 WebSocket 连接
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
      await _channel!.ready;

      // 连接成功，更新状态并启动心跳
      _setStatus(WsConnectionStatus.connected);
      _reconnectAttempts = 0; // 重置重连次数
      _startHeartbeat();

      // 监听 WebSocket 消息流
      _subscription = _channel!.stream.listen(
        _onMessage, // 消息处理回调
        onError: _onError, // 错误处理回调
        onDone: _onDone, // 连接关闭回调
        cancelOnError: false, // 错误时不自动取消订阅
      );
    } catch (e) {
      // 连接失败，更新状态并调度重连
      _setStatus(WsConnectionStatus.disconnected);
      _scheduleReconnect();
    }
  }

  /// 发送聊天消息
  ///
  /// 通过 WebSocket 发送用户消息到服务器
  ///
  /// [text] 消息文本内容
  /// [postContext] 可选的帖子上下文（从帖子发起聊天时传入）
  void sendMessage(String text, {String? postContext}) {
    _send({
      'type': 'message',
      'data': {
        'text': text,
        if (postContext != null) 'post_context': postContext,
      },
    });
  }

  /// 发送心跳 ping 消息
  ///
  /// 通常由心跳定时器自动调用
  void sendPing() {
    _send({'type': 'ping'});
  }

  /// 主动断开连接
  ///
  /// 设置 intentionalDisconnect 标志，不触发自动重连
  void disconnect() {
    _intentionalDisconnect = true;
    _dispose();
  }

  /// 释放资源并关闭消息流
  ///
  /// 在组件销毁时调用，确保完全清理资源
  void dispose() {
    _disposed = true;
    _dispose();
    _messageController.close(); // 关闭消息广播流
  }

  /// 发送 WebSocket 消息
  ///
  /// 内部方法，将消息序列化为 JSON 并发送
  ///
  /// [message] 消息对象（Map 格式）
  void _send(Map<String, dynamic> message) {
    // 检查连接状态，未连接时发送错误消息
    if (_channel == null || _status != WsConnectionStatus.connected) {
      _messageController.add({
        'type': WsMessageType.error,
        'data': {'code': 'not_connected', 'detail': 'WebSocket not connected'},
      });
      return;
    }
    // 发送 JSON 序列化的消息
    _channel!.sink.add(jsonEncode(message));
  }

  /// 处理接收的消息
  ///
  /// 解析 JSON 消息并根据类型分发
  ///
  /// [message] 原始消息字符串
  void _onMessage(dynamic message) {
    // 收到消息时取消 pong 超时计时
    _cancelPongTimeout();

    try {
      // 解析 JSON 消息
      final data = jsonDecode(message as String) as Map<String, dynamic>;
      final type = data['type'] as String?;

      // pong 消息是心跳响应，无需广播
      if (type == 'pong') {
        return;
      }

      // 将消息广播给监听者
      _messageController.add(data);
    } catch (e) {
      // 解析失败时发送错误消息
      _messageController.add({
        'type': WsMessageType.error,
        'data': {'code': 'parse_error', 'detail': 'Failed to parse message'},
      });
    }
  }

  /// 处理 WebSocket 错误
  ///
  /// [error] 错误对象
  void _onError(dynamic error) {
    _setStatus(WsConnectionStatus.disconnected);
    _stopHeartbeat();
    _scheduleReconnect();
  }

  /// 处理 WebSocket 连接关闭
  ///
  /// 连接关闭时检查是否需要重连
  void _onDone() {
    _setStatus(WsConnectionStatus.disconnected);
    _stopHeartbeat();

    // 如果不是主动断开且未释放，尝试重连
    if (!_intentionalDisconnect && !_disposed) {
      _scheduleReconnect();
    }
  }

  /// 设置连接状态
  ///
  /// 状态变化时触发 onStatusChange 回调
  ///
  /// [newStatus] 新的连接状态
  void _setStatus(WsConnectionStatus newStatus) {
    if (_status != newStatus) {
      _status = newStatus;
      onStatusChange?.call(newStatus);
    }
  }

  /// 启动心跳定时器
  ///
  /// 每 30 秒发送一次 ping，检测连接是否存活
  void _startHeartbeat() {
    _stopHeartbeat(); // 先停止之前的定时器

    _heartbeatTimer = Timer.periodic(_heartbeatInterval, (_) {
      if (_status == WsConnectionStatus.connected) {
        sendPing(); // 发送 ping
        _startPongTimeout(); // 启动 pong 超时计时
      }
    });
  }

  /// 停止心跳定时器
  void _stopHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _cancelPongTimeout();
  }

  /// 启动 pong 响应超时计时
  ///
  /// 如果 10 秒内未收到 pong，认为连接已断开
  void _startPongTimeout() {
    _cancelPongTimeout();

    _pongTimeoutTimer = Timer(_pongTimeout, () {
      // pong 未响应，连接可能已断开
      _channel?.sink.close();
      _setStatus(WsConnectionStatus.disconnected);
      _scheduleReconnect();
    });
  }

  /// 取消 pong 超时计时
  void _cancelPongTimeout() {
    _pongTimeoutTimer?.cancel();
    _pongTimeoutTimer = null;
  }

  /// 调度重连
  ///
  /// 使用指数退避策略：1s, 2s, 4s, 8s, 16s, 最大 30s
  void _scheduleReconnect() {
    // 检查是否需要重连
    if (_disposed || _intentionalDisconnect) return;

    // 达到最大重连次数时发送错误消息
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

    // 指数退避：1s, 2s, 4s, 8s, 16s, 最大 30s
    final delay = Duration(
      seconds: _clamp(1 << _reconnectAttempts, 1, 30),
    );
    _reconnectAttempts++;

    _setStatus(WsConnectionStatus.reconnecting);

    // 延迟后尝试重连
    _reconnectTimer = Timer(delay, () {
      if (!_disposed && !_intentionalDisconnect) {
        connect();
      }
    });
  }

  /// 内部资源释放方法
  ///
  /// 关闭定时器、取消订阅、关闭连接
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

  /// 数值范围约束辅助方法
  ///
  /// [value] 待约束的值
  /// [min] 最小值
  /// [max] 最大值
  ///
  /// 返回约束后的值
  int _clamp(int value, int min, int max) {
    if (value < min) return min;
    if (value > max) return max;
    return value;
  }
}
