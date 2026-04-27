// ============================================================================
// SoulPulse 聊天页面
// ============================================================================
//
// 本文件提供与 AI 人设的实时聊天界面，包含：
// - WebSocket 实时消息收发
// - 历史消息加载与分页
// - AI 情绪状态显示
// - 消息气泡渲染（用户消息、AI回复、主动消息等）
// - 消息操作菜单（复制、删除）
// - 连接状态指示器
// - 正在输入动画效果
//
// 主要组件：
// - ChatPage: 页面根组件
// - _ChatMsg: 聊天消息数据模型
// - _MessageBubble: 消息气泡组件
// - _TypingIndicator: 正在输入动画组件
//
// ============================================================================

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/api/api_client.dart';
import '../../core/api/ws_client.dart';
import '../../core/theme/character_theme.dart';

/// 聊天页面组件
///
/// 提供与指定 AI 的实时聊天功能。
/// 支持从帖子发起带上下文的聊天。
///
/// 参数：
/// - aiId: AI 人设的 ID
/// - aiName: AI 名称（用于显示）
/// - postContext: 可选的帖子上下文（从帖子发起聊天时传入）
class ChatPage extends StatefulWidget {
  /// 目标 AI 的 ID
  final int aiId;

  /// AI 名称（用于页面标题显示）
  final String aiName;

  /// 帖子上下文（可选）
  ///
  /// 从帖子发起聊天时，将帖子内容作为上下文传递给 AI
  final String? postContext;

  /// 构造函数
  const ChatPage({
    super.key,
    required this.aiId,
    required this.aiName,
    this.postContext,
  });

  @override
  State<ChatPage> createState() => _ChatPageState();
}

/// 聊天页面状态类
///
/// 使用 TickerProviderStateMixin 以支持动画控制器。
///
/// 管理功能：
/// - WebSocket 连接与消息监听
/// - 历史消息加载与分页滚动
/// - 消息发送与状态更新
/// - AI 情绪状态获取
/// - 消息删除与复制
/// - 正在输入动画
class _ChatPageState extends State<ChatPage> with TickerProviderStateMixin {
  /// 消息输入框控制器
  final _messageCtrl = TextEditingController();

  /// 消息列表滚动控制器
  final _scrollCtrl = ScrollController();

  /// 本地消息列表
  ///
  /// 包含用户发送的消息和 AI 回复的消息
  final List<_ChatMsg> _messages = [];

  /// WebSocket 客户端实例
  WsClient? _wsClient;

  /// WebSocket 消息流订阅
  StreamSubscription? _wsSub;

  /// 当前 WebSocket 连接状态
  WsConnectionStatus _connectionStatus = WsConnectionStatus.disconnected;

  /// 是否正在发送消息（用于显示加载状态）
  bool _sending = false;

  /// 是否正在加载历史消息
  bool _loadingHistory = false;

  /// 是否还有更多历史消息可加载
  bool _hasMoreHistory = true;

  /// 已加载的最旧消息 ID（用于分页加载）
  int? _oldestMessageId;

  /// AI 当前情绪状态（用于状态栏显示）
  String? _emotionMood;

  /// AI 能量等级 (tired / normal / energetic)
  String? _energyLevel;

  /// AI 是否在思念用户
  bool _longing = false;

  /// AI 角色本地时间（如 "22:30"）
  String? _personaLocalTime;

  /// AI 角色时区（如 "Asia/Shanghai"）
  String? _personaTimezone;

  /// 正在输入动画控制器
  ///
  /// 使用 TickerProviderStateMixin 提供 vsync
  late AnimationController _typingAnimCtrl;

  @override
  void initState() {
    super.initState();

    // 监听滚动事件，实现向上滚动时加载更多历史消息
    _scrollCtrl.addListener(_onScroll);

    // 初始化正在输入动画控制器
    _typingAnimCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(); // 循环播放动画

    // 加载历史消息
    _loadHistory();

    // 建立 WebSocket 连接
    _connectWebSocket();

    // 加载 AI 情绪状态
    _loadEmotionStatus();
  }

  @override
  void dispose() {
    // 离开页面时标记对话为已读
    ApiClient.post('/api/chat/mark-read/${widget.aiId}', {})
        .catchError((_) => <String, dynamic>{});

    // 清理监听器和控制器
    _scrollCtrl.removeListener(_onScroll);
    _scrollCtrl.dispose();
    _messageCtrl.dispose();
    _typingAnimCtrl.dispose();

    // 取消 WebSocket 订阅并释放客户端
    _wsSub?.cancel();
    _wsClient?.dispose();

    super.dispose();
  }

  // ================== 情绪状态加载 ==================

  /// 加载 AI 当前情绪状态
  ///
  /// 获取 AI 的 mood 字段并更新状态栏显示
  Future<void> _loadEmotionStatus() async {
    try {
      final data = await ApiClient.get('/api/ai/emotion/${widget.aiId}');
      if (mounted) {
        setState(() {
          _emotionMood = data['mood'] as String?;
          _energyLevel = data['energy_level'] as String?;
          _longing = (data['longing'] as bool?) ?? false;
          _personaLocalTime = data['persona_local_time'] as String?;
          _personaTimezone = data['persona_timezone'] as String?;
        });
      }
    } catch (_) {
      // 加载失败时静默处理
    }
  }

  // ================== 历史消息加载 ==================

  /// 加载聊天历史消息
  ///
  /// 支持分页加载：
  /// - 首次加载获取最近 30 条消息
  /// - 向上滚动时加载更早的消息
  ///
  /// [beforeId] 分页加载时传入最旧消息 ID，获取更早的消息
  Future<void> _loadHistory({int? beforeId}) async {
    // 防止重复加载
    if (_loadingHistory) return;
    if (beforeId == null && !_hasMoreHistory) return;

    setState(() => _loadingHistory = true);

    try {
      // 构造 API 路径
      String path = '/api/chat/history/${widget.aiId}?limit=30';
      if (beforeId != null) path += '&before_id=$beforeId';

      // 获取历史消息
      final result = await ApiClient.get(path, useCache: false);
      final List<dynamic> messagesJson = result['messages'] ?? [];
      final hasMore = result['has_more'] ?? false;

      // 解析消息列表
      final newMessages =
          messagesJson.map((m) => _ChatMsg.fromJson(m)).toList();

      if (mounted) {
        setState(() {
          if (beforeId != null) {
            // 分页加载：在列表开头插入新消息
            _messages.insertAll(0, newMessages);
          } else {
            // 首次加载：清空并重新填充消息列表
            _messages.clear();

            // 如果有帖子上下文，添加上下文提示消息
            if (widget.postContext != null && widget.postContext!.isNotEmpty) {
              _messages.add(_ChatMsg(
                text: 'Regarding post: "${widget.postContext}"',
                isUser: false,
                isContext: true, // 标记为上下文消息
              ));
            }

            _messages.addAll(newMessages);
          }

          // 更新分页状态
          _hasMoreHistory = hasMore;
          if (newMessages.isNotEmpty) {
            _oldestMessageId = newMessages.first.id;
          }
          _loadingHistory = false;
        });

        // 首次加载时滚动到底部
        if (beforeId == null) _scrollToBottom();
      }
    } catch (e) {
      if (mounted) setState(() => _loadingHistory = false);
    }
  }

  /// 滚动监听回调
  ///
  /// 当用户滚动到顶部附近时，触发加载更多历史消息
  void _onScroll() {
    if (_scrollCtrl.position.pixels < 100 &&
        _hasMoreHistory &&
        !_loadingHistory &&
        _oldestMessageId != null) {
      _loadHistory(beforeId: _oldestMessageId);
    }
  }

  // ================== WebSocket 连接管理 ==================

  /// 建立 WebSocket 连接
  ///
  /// 创建 WsClient 实例并监听消息流
  void _connectWebSocket() {
    _wsClient = WsClient(
      aiId: widget.aiId,
      onStatusChange: (status) {
        // 更新连接状态（用于 UI 显示）
        if (mounted) setState(() => _connectionStatus = status);
      },
    );

    // 监听 WebSocket 消息
    _wsSub = _wsClient!.messages.listen(_onWsMessage);

    // 建立连接
    _wsClient!.connect();
  }

  /// WebSocket 消息处理回调
  ///
  /// 根据消息类型分发到相应的处理方法
  ///
  /// [msg] WebSocket 消息数据（Map 格式）
  void _onWsMessage(Map<String, dynamic> msg) {
    final type = msg['type'] as String?;
    final data = msg['data'] as Map<String, dynamic>? ?? {};

    // 根据消息类型处理
    switch (type) {
      case WsMessageType.aiReply:
        _onAiReply(data);
        break;
      case WsMessageType.proactiveDm:
        _onProactiveDm(data);
        break;
      case WsMessageType.messageSaved:
        // 消息保存确认，无需特殊处理
        break;
      case WsMessageType.error:
        _onWsError(data);
        break;
    }
  }

  /// 处理 AI 回复消息
  ///
  /// 将 AI 回复添加到消息列表
  ///
  /// [data] 回复消息数据
  void _onAiReply(Map<String, dynamic> data) {
    final text = data['text'] as String? ?? '';
    final messageId = data['message_id'] as int?;
    final timestamp = data['created_at'] as String?;

    setState(() {
      // 停止发送状态
      _sending = false;

      // 添加 AI 回复消息
      _messages.add(_ChatMsg(
        id: messageId,
        text: text,
        isUser: false,
        timestamp: timestamp ?? DateTime.now().toIso8601String(),
      ));
    });

    _scrollToBottom();
  }

  /// 处理 AI 主动发送的消息
  ///
  /// AI 可能主动向用户发送问候或关心消息
  ///
  /// [data] 主动消息数据
  void _onProactiveDm(Map<String, dynamic> data) {
    final text = data['text'] as String? ?? '';
    final messageId = data['message_id'] as int?;
    final event = data['event'] as String?; // 事件类型标签

    setState(() {
      _messages.add(_ChatMsg(
        id: messageId,
        text: text,
        isUser: false,
        messageType: 'proactive_dm', // 标记为主动消息
        event: event,
        timestamp: DateTime.now().toIso8601String(),
      ));
    });

    _scrollToBottom();
  }

  /// 处理 WebSocket 错误
  ///
  /// 显示错误消息并停止发送状态
  ///
  /// [data] 错误数据
  void _onWsError(Map<String, dynamic> data) {
    final detail = data['detail'] as String? ?? 'Unknown error';

    if (_sending) {
      setState(() {
        _sending = false;

        // 添加错误提示消息
        _messages.add(_ChatMsg(
          text: 'Failed to send: $detail',
          isUser: false,
          isError: true, // 标记为错误消息
        ));
      });
    }
  }

  // ================== 消息发送 ==================

  /// 发送用户消息
  ///
  /// 通过 WebSocket 或 REST API 发送消息
  /// WebSocket 断开时自动降级到 REST API
  Future<void> _send() async {
    final text = _messageCtrl.text.trim();
    if (text.isEmpty) return;

    setState(() {
      // 添加用户消息到本地列表
      _messages.add(_ChatMsg(
        text: text,
        isUser: true,
        timestamp: DateTime.now().toIso8601String(),
      ));

      // 清空输入框
      _messageCtrl.clear();

      // 设置发送状态
      _sending = true;
    });

    _scrollToBottom();

    // 根据连接状态选择发送方式
    if (_connectionStatus == WsConnectionStatus.connected &&
        _wsClient != null) {
      // WebSocket 连接正常，通过 WebSocket 发送
      _wsClient!.sendMessage(text, postContext: widget.postContext);
    } else {
      // WebSocket 断开，降级到 REST API
      await _sendViaRest(text);
    }
  }

  /// 通过 REST API 发送消息
  ///
  /// WebSocket 断开时的降级方案
  ///
  /// [text] 消息文本
  Future<void> _sendViaRest(String text) async {
    try {
      final result = await ApiClient.post('/api/chat/send', {
        'ai_id': widget.aiId,
        'message': text,
        if (widget.postContext != null) 'post_context': widget.postContext,
      });

      if (mounted) {
        setState(() {
          _sending = false;

          // 添加 AI 回复
          _messages.add(_ChatMsg(
            id: result['message_id'] as int?,
            text: result['reply'] ?? '...',
            isUser: false,
            timestamp: DateTime.now().toIso8601String(),
          ));
        });
        _scrollToBottom();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _sending = false;

          // 显示错误提示
          _messages.add(_ChatMsg(
            text: 'Failed to get reply. Please try again.',
            isUser: false,
            isError: true,
          ));
        });
      }
    }
  }

  // ================== 消息删除 ==================

  /// 删除消息
  ///
  /// 仅支持删除用户发送的消息
  ///
  /// [index] 消息在列表中的索引
  Future<void> _deleteMessage(int index) async {
    final msg = _messages[index];

    // 仅允许删除有 ID 的用户消息
    if (msg.id == null || !msg.isUser) return;

    try {
      await ApiClient.delete('/api/chat/messages/${msg.id}');

      if (mounted) {
        setState(() => _messages.removeAt(index));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to delete message')),
        );
      }
    }
  }

  /// 显示消息操作菜单
  ///
  /// 长按消息时弹出菜单，提供复制和删除选项
  ///
  /// [index] 消息在列表中的索引
  void _showMessageMenu(int index) {
    final msg = _messages[index];

    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            /// 复制文本选项
            ListTile(
              leading: const Icon(Icons.copy),
              title: const Text('Copy text'),
              onTap: () {
                Clipboard.setData(ClipboardData(text: msg.text));
                Navigator.pop(ctx);
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                      content: Text('Copied to clipboard'),
                      duration: Duration(seconds: 1)),
                );
              },
            ),

            /// 删除选项（仅对用户消息显示）
            if (msg.isUser && msg.id != null)
              ListTile(
                leading: const Icon(Icons.delete, color: Colors.red),
                title:
                    const Text('Delete', style: TextStyle(color: Colors.red)),
                onTap: () {
                  Navigator.pop(ctx);
                  _deleteMessage(index);
                },
              ),
          ],
        ),
      ),
    );
  }

  /// 滚动到底部
  ///
  /// 发送或收到新消息后自动滚动
  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  // ================== UI 辅助方法 ==================

  /// 获取连接状态文本
  ///
  /// 用于 AppBar 状态栏显示
  String get _statusText {
    switch (_connectionStatus) {
      case WsConnectionStatus.connected:
        // 显示 AI 当前情绪状态
        if (_emotionMood != null) {
          return 'Feeling $_emotionMood';
        }
        return 'Active now';
      case WsConnectionStatus.connecting:
        return 'Connecting...';
      case WsConnectionStatus.reconnecting:
        return 'Reconnecting...';
      case WsConnectionStatus.disconnected:
        return 'Offline';
    }
  }

  /// 获取连接状态颜色
  ///
  /// 根据状态和情绪返回对应的颜色
  Color get _statusColor {
    switch (_connectionStatus) {
      case WsConnectionStatus.connected:
        return _moodColor(_emotionMood);
      case WsConnectionStatus.connecting:
      case WsConnectionStatus.reconnecting:
        return Colors.orange; // 等待状态
      case WsConnectionStatus.disconnected:
        return Colors.grey; // 断开状态
    }
  }

  /// 根据情绪获取对应颜色
  ///
  /// [mood] 情绪类型字符串
  Color _moodColor(String? mood) {
    switch (mood) {
      case 'joyful':
        return Colors.amber; // 快乐：琥珀色
      case 'good':
        return Colors.green; // 良好：绿色
      case 'neutral':
        return Colors.blue; // 中性：蓝色
      case 'subdued':
        return Colors.orange; // 低落：橙色
      case 'melancholic':
        return Colors.indigo; // 悲伤：靛蓝色
      default:
        return Colors.green;
    }
  }

  /// 判断是否需要显示日期分隔符
  ///
  /// 在不同日期的消息之间显示日期标签
  ///
  /// [index] 当前消息索引
  bool _shouldShowDateSeparator(int index) {
    if (index == 0) return true;

    final current = _messages[index].timestamp;
    final prev = _messages[index - 1].timestamp;

    if (current == null || prev == null) return false;

    try {
      final currentDate = DateTime.parse(current).toLocal();
      final prevDate = DateTime.parse(prev).toLocal();

      // 如果日期不同，显示分隔符
      return currentDate.day != prevDate.day ||
          currentDate.month != prevDate.month ||
          currentDate.year != prevDate.year;
    } catch (_) {
      return false;
    }
  }

  /// 格式化日期分隔符文本
  ///
  /// 显示 "Today"、"Yesterday" 或具体日期
  ///
  /// [isoString] ISO 8601 格式的时间字符串
  String _formatDateSeparator(String? isoString) {
    if (isoString == null) return '';

    try {
      final dt = DateTime.parse(isoString).toLocal();
      final now = DateTime.now();

      // 今天
      if (dt.year == now.year && dt.month == now.month && dt.day == now.day) {
        return 'Today';
      }

      // 昨天
      final yesterday = now.subtract(const Duration(days: 1));
      if (dt.year == yesterday.year &&
          dt.month == yesterday.month &&
          dt.day == yesterday.day) {
        return 'Yesterday';
      }

      // 其他日期：显示月/日/年
      return '${dt.month}/${dt.day}/${dt.year}';
    } catch (_) {
      return '';
    }
  }

  // ================== 页面构建 ==================

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final characterColors = CharacterTheme.getPalette(widget.aiName);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.pop(),
        ),

        /// AppBar 标题区域
        ///
        /// 点击可导航到 AI 详情页面
        title: GestureDetector(
          onTap: () {
            final aiName = Uri.encodeComponent(widget.aiName);
            context.push('/ai/${widget.aiId}?name=$aiName');
          },
          child: Row(
            children: [
              /// AI 头像 with character-colored border
              Container(
                padding: const EdgeInsets.all(2),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: characterColors.primary,
                    width: 2,
                  ),
                ),
                child: CircleAvatar(
                  radius: 14,
                  backgroundColor: Colors.grey[300],
                  child: Text(
                    widget.aiName[0], // 显示名称首字母
                    style: GoogleFonts.inter(
                        fontWeight: FontWeight.w600, color: Colors.grey[700]),
                  ),
                ),
              ),

              const SizedBox(width: 10),

              /// AI 名称和状态
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    /// AI 名称 with character color and accent dot
                    Row(
                      children: [
                        Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            color: characterColors.primary,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          widget.aiName,
                          style: GoogleFonts.inter(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                            color: characterColors.primary,
                          ),
                        ),
                      ],
                    ),

                    /// 连接状态指示
                    Row(
                      children: [
                        /// 状态指示点
                        Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            color: _statusColor,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 4),

                        /// 状态文本
                        Text(
                          _statusText,
                          style: GoogleFonts.inter(
                              fontSize: 11, color: _statusColor),
                        ),
                      ],
                    ),

                    /// 时区提示（当 AI 角色时区与用户设备时区不同时显示）
                    if (_personaLocalTime != null &&
                        _personaLocalTime!.isNotEmpty &&
                        _personaTimezone != null &&
                        _personaTimezone!.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          'Their time: $_personaLocalTime',
                          style: GoogleFonts.inter(
                            fontSize: 10,
                            color: Colors.grey[500],
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(2),
          child: Container(
            height: 2,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  characterColors.primary.withValues(alpha: 0.0),
                  characterColors.primary.withValues(alpha: 0.3),
                  characterColors.primary.withValues(alpha: 0.0),
                ],
              ),
            ),
          ),
        ),
      ),
      body: Column(
        children: [
          // ================== 情绪状态栏 ==================
          /// 显示 AI 当前能量、心情和思念状态
          _EmotionStatusBar(
            energyLevel: _energyLevel,
            mood: _emotionMood,
            longing: _longing,
            characterColors: characterColors,
            isConnected: _connectionStatus == WsConnectionStatus.connected,
          ),

          // ================== 顶部加载指示器 ==================
          /// 分页加载历史消息时显示
          if (_loadingHistory)
            const Padding(
              padding: EdgeInsets.all(8),
              child: SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2)),
            ),

          // ================== 消息列表 ==================
          Expanded(
            child: _messages.isEmpty && !_loadingHistory
                // 无消息时的空状态提示
                ? Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.chat_bubble_outline,
                            size: 48, color: Colors.grey[300]),
                        const SizedBox(height: 16),
                        Text('Say hi to ${widget.aiName}!',
                            style: GoogleFonts.inter(
                                fontSize: 15, color: Colors.grey[500])),
                      ],
                    ),
                  )
                // 消息列表
                : ListView.builder(
                    controller: _scrollCtrl,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 12),
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      final msg = _messages[index];
                      final showDate = _shouldShowDateSeparator(index);

                      return Column(
                        children: [
                          /// 日期分隔符
                          if (showDate)
                            Padding(
                              padding: const EdgeInsets.symmetric(vertical: 12),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Container(
                                      height: 1,
                                      color: Colors.grey.withValues(alpha: 0.3),
                                    ),
                                  ),
                                  Padding(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 12),
                                    child: Text(
                                      _formatDateSeparator(msg.timestamp),
                                      style: GoogleFonts.inter(
                                          fontSize: 12,
                                          color: Colors.grey[500]),
                                    ),
                                  ),
                                  Expanded(
                                    child: Container(
                                      height: 1,
                                      color: Colors.grey.withValues(alpha: 0.3),
                                    ),
                                  ),
                                ],
                              ),
                            ),

                          /// 消息气泡（长按显示操作菜单）
                          GestureDetector(
                            onLongPress: () => _showMessageMenu(index),
                            child: _MessageBubble(
                              msg: msg,
                              isDark: isDark,
                              characterColors: characterColors,
                            ),
                          ),
                        ],
                      );
                    },
                  ),
          ),

          // ================== 正在输入指示器 ==================
          /// AI 正在回复时显示动画
          if (_sending)
            Padding(
              padding: const EdgeInsets.only(left: 20, bottom: 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: _TypingIndicator(
                  animationController: _typingAnimCtrl,
                  aiName: widget.aiName,
                  dotColor: characterColors.primary,
                ),
              ),
            ),

          // ================== 消息输入栏 ==================
          Container(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surface,
              border: Border(
                top: BorderSide(
                  color: Theme.of(context).dividerTheme.color ??
                      Theme.of(context)
                          .colorScheme
                          .outline
                          .withValues(alpha: 0.2),
                ),
              ),
            ),
            child: SafeArea(
              top: false,
              child: Row(
                children: [
                  /// 消息输入框
                  Expanded(
                    child: TextField(
                      controller: _messageCtrl,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _send(), // 回车发送
                      decoration: InputDecoration(
                        hintText: 'Message...',
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(24),
                          borderSide: BorderSide(
                            color: Theme.of(context).dividerTheme.color ??
                                Theme.of(context)
                                    .colorScheme
                                    .outline
                                    .withValues(alpha: 0.3),
                          ),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(24),
                          borderSide: BorderSide(
                            color: Theme.of(context).dividerTheme.color ??
                                Theme.of(context)
                                    .colorScheme
                                    .outline
                                    .withValues(alpha: 0.3),
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(24),
                          borderSide: BorderSide(
                            color: Theme.of(context).colorScheme.primary,
                            width: 1,
                          ),
                        ),
                        filled: true,
                        fillColor: Theme.of(context).colorScheme.surface,
                        contentPadding: const EdgeInsets.symmetric(
                            horizontal: 20, vertical: 10),
                      ),
                    ),
                  ),

                  const SizedBox(width: 8),

                  /// 发送按钮
                  GestureDetector(
                    onTap: _sending ? null : _send,
                    child: Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.primary,
                        shape: BoxShape.circle,
                      ),
                      child:
                          const Icon(Icons.send, color: Colors.white, size: 20),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================================
// 正在输入动画组件
// ============================================================================
//
/// 显示 AI 正在输入的动画指示器
///
/// 使用三个动态弹跳的圆点模拟输入效果
class _TypingIndicator extends StatelessWidget {
  /// 动画控制器
  final AnimationController animationController;

  /// AI 名称（用于显示前缀文本）
  final String aiName;

  /// 圆点颜色
  final Color dotColor;

  /// 构造函数
  const _TypingIndicator({
    required this.animationController,
    required this.aiName,
    this.dotColor = Colors.grey,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        /// AI 名称前缀
        Text(
          '$aiName is typing ',
          style: GoogleFonts.inter(
              fontSize: 12, color: Colors.grey, fontStyle: FontStyle.italic),
        ),

        /// 动画圆点
        AnimatedBuilder(
          animation: animationController,
          builder: (context, child) {
            return Row(
              mainAxisSize: MainAxisSize.min,
              children: List.generate(3, (i) {
                // 每个圆点有不同的延迟，创建波浪弹跳效果
                final delay = i * 0.15;
                final progress = (animationController.value - delay) % 1.0;

                // 使用正弦波创建弹跳效果
                final bounce = (progress < 0.5)
                    ? progress * 2 // 上升阶段
                    : 2 - progress * 2; // 下降阶段

                // 弹跳高度（向上移动）
                final yOffset = -bounce * 4;

                // 透明度变化
                final opacity = 0.4 + bounce * 0.6;

                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 1.5),
                  child: Transform.translate(
                    offset: Offset(0, yOffset),
                    child: Container(
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(
                        color: dotColor.withValues(alpha: opacity),
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                );
              }),
            );
          },
        ),
      ],
    );
  }
}

// ============================================================================
// 情绪状态栏组件
// ============================================================================
//
/// 显示 AI 当前情绪状态的紧凑状态栏
///
/// 包含：
/// - 能量指示条（能量等级）
/// - 心情表情符号
/// - 思念指示器（可选）
class _EmotionStatusBar extends StatelessWidget {
  /// 能量等级: "tired" / "normal" / "energetic"
  final String? energyLevel;

  /// 心情: "melancholic" / "subdued" / "neutral" / "good" / "joyful"
  final String? mood;

  /// 是否在思念用户
  final bool longing;

  /// 角色配色
  final CharacterColors characterColors;

  /// 是否已连接
  final bool isConnected;

  const _EmotionStatusBar({
    required this.energyLevel,
    required this.mood,
    required this.longing,
    required this.characterColors,
    required this.isConnected,
  });

  /// 获取能量等级对应的填充比例
  double _getEnergyFill() {
    switch (energyLevel) {
      case 'tired':
        return 0.25;
      case 'normal':
        return 0.6;
      case 'energetic':
        return 1.0;
      default:
        return 0.6;
    }
  }

  /// 获取能量等级对应的颜色
  Color _getEnergyColor() {
    switch (energyLevel) {
      case 'tired':
        return Colors.grey;
      case 'normal':
        return Colors.blue;
      case 'energetic':
        return Colors.green;
      default:
        return Colors.blue;
    }
  }

  /// 获取心情对应的表情符号
  String _getMoodEmoji() {
    switch (mood) {
      case 'melancholic':
        return '😔';
      case 'subdued':
        return '😐';
      case 'neutral':
        return '🙂';
      case 'good':
        return '😊';
      case 'joyful':
        return '😄';
      default:
        return '🙂';
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    // 未连接时不显示状态栏
    if (!isConnected) {
      return const SizedBox.shrink();
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      decoration: BoxDecoration(
        color: isDark
            ? characterColors.primary.withValues(alpha: 0.1)
            : characterColors.primary.withValues(alpha: 0.05),
        border: Border(
          bottom: BorderSide(
            color: characterColors.primary.withValues(alpha: 0.1),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          /// 能量指示条
          Expanded(
            child: Row(
              children: [
                /// 能量图标
                Icon(
                  Icons.bolt,
                  size: 12,
                  color: _getEnergyColor(),
                ),
                const SizedBox(width: 4),

                /// 能量进度条
                Expanded(
                  child: Container(
                    height: 4,
                    decoration: BoxDecoration(
                      color: Colors.grey.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(2),
                    ),
                    child: FractionallySizedBox(
                      alignment: Alignment.centerLeft,
                      widthFactor: _getEnergyFill(),
                      child: Container(
                        decoration: BoxDecoration(
                          color: _getEnergyColor(),
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(width: 12),

          /// 心情表情
          Text(
            _getMoodEmoji(),
            style: const TextStyle(fontSize: 14),
          ),

          /// 思念指示器
          if (longing) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: characterColors.accent.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '💭',
                    style: const TextStyle(fontSize: 10),
                  ),
                  const SizedBox(width: 2),
                  Text(
                    'Missing you',
                    style: GoogleFonts.inter(
                      fontSize: 9,
                      color: characterColors.primary,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

// ============================================================================
// 聊天消息数据模型
// ============================================================================
//
/// 聊天消息数据类
///
/// 存储单条消息的所有信息
class _ChatMsg {
  /// 消息 ID（用于删除等操作）
  final int? id;

  /// 消息文本内容
  final String text;

  /// 是否为用户发送的消息
  final bool isUser;

  /// 是否为上下文提示消息
  ///
  /// 从帖子发起聊天时，显示帖子内容作为上下文
  final bool isContext;

  /// 是否为错误提示消息
  final bool isError;

  /// 消息类型
  ///
  /// 可选值：'chat', 'proactive_dm'
  final String messageType;

  /// 事件类型标签（用于主动消息）
  ///
  /// 如 'morning_greeting', 'care_reminder' 等
  final String? event;

  /// 消息时间戳（ISO 8601 格式）
  final String? timestamp;

  /// 构造函数
  _ChatMsg({
    this.id,
    required this.text,
    required this.isUser,
    this.isContext = false,
    this.isError = false,
    this.messageType = 'chat',
    this.event,
    this.timestamp,
  });

  /// 从 JSON 数据创建消息对象
  ///
  /// 用于解析历史消息 API 返回的数据
  ///
  /// [json] API 返回的消息 JSON 对象
  factory _ChatMsg.fromJson(Map<String, dynamic> json) {
    final role = json['role'] as String? ?? 'assistant';

    return _ChatMsg(
      id: json['id'] as int?,
      text: json['content'] as String? ?? '',
      isUser: role == 'user',
      messageType: json['message_type'] as String? ?? 'chat',
      event: json['event'] as String?,
      timestamp: json['created_at'] as String?,
    );
  }
}

// ============================================================================
// 消息气泡组件
// ============================================================================
//
/// 消息气泡 Widget
///
/// 根据消息类型渲染不同样式的气泡：
/// - 用户消息：蓝色气泡，右对齐
/// - AI 回复：灰色气泡，左对齐
/// - 上下文消息：绿色背景，带链接图标
/// - 主动消息：粉色背景，带事件标签
/// - 错误消息：红色背景
class _MessageBubble extends StatelessWidget {
  /// 消息数据
  final _ChatMsg msg;

  /// 是否为深色模式
  final bool isDark;

  /// 角色配色
  final CharacterColors characterColors;

  /// 构造函数
  const _MessageBubble({
    required this.msg,
    required this.isDark,
    required this.characterColors,
  });

  /// 格式化时间显示
  ///
  /// 显示 HH:MM 格式的时间
  ///
  /// [isoString] ISO 8601 格式的时间字符串
  String _formatTime(String? isoString) {
    if (isoString == null) return '';

    try {
      final dt = DateTime.parse(isoString).toLocal();
      final hour = dt.hour.toString().padLeft(2, '0');
      final minute = dt.minute.toString().padLeft(2, '0');
      return '$hour:$minute';
    } catch (_) {
      return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    // ================== 上下文消息气泡 ==================
    /// 从帖子发起聊天时显示的上下文提示
    if (msg.isContext) {
      return Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isDark
              ? const Color(0xFF1A2A1A)
              : const Color(0xFFE8F5E9), // 绿色背景
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            const Icon(Icons.link, size: 16, color: Colors.green),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                msg.text,
                style: GoogleFonts.inter(
                  fontSize: 13,
                  fontStyle: FontStyle.italic,
                  color: isDark ? Colors.green[200] : Colors.green[800],
                ),
              ),
            ),
          ],
        ),
      );
    }

    // ================== 主动消息气泡 ==================
    /// AI 主动发送的消息（问候、关心等）
    if (msg.messageType == 'proactive_dm') {
      return Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isDark
              ? const Color(0xFF2A1A2A)
              : const Color(0xFFFCE4EC), // 粉色背景
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isDark ? Colors.pink[800]! : Colors.pink[200]!,
            width: 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            /// 事件类型标签
            if (msg.event != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  msg.event!,
                  style: GoogleFonts.inter(
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: isDark ? Colors.pink[200] : Colors.pink[400],
                  ),
                ),
              ),

            /// 消息内容
            Text(
              msg.text,
              style: GoogleFonts.inter(
                  fontSize: 14, color: isDark ? Colors.white : Colors.black87),
            ),

            /// 时间戳
            if (msg.timestamp != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  _formatTime(msg.timestamp),
                  style:
                      GoogleFonts.inter(fontSize: 11, color: Colors.grey[500]),
                ),
              ),
          ],
        ),
      );
    }

    // ================== 常规消息气泡 ==================
    /// 用户消息或 AI 回复

    /// 背景颜色
    final bgColor = msg.isUser
        ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.10)
        : msg.isError
            ? Colors.red.withValues(alpha: 0.15) // 错误消息：红色半透明
            : characterColors.primary
                .withValues(alpha: isDark ? 0.12 : 0.08); // AI 回复：角色主色低透明度

    /// 文字颜色
    final textColor =
        msg.isError ? Colors.red : Theme.of(context).colorScheme.onSurface;

    /// 时间戳颜色
    final timeColor = msg.isError
        ? Colors.red.withValues(alpha: 0.7)
        : Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.5);

    return Align(
      // 用户消息右对齐，AI 消息左对齐
      alignment: msg.isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        constraints:
            BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
        decoration: BoxDecoration(
          color: bgColor,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(18),
            topRight: const Radius.circular(18),
            // 消息尾巴效果
            bottomLeft: Radius.circular(msg.isUser ? 18 : 4),
            bottomRight: Radius.circular(msg.isUser ? 4 : 18),
          ),
        ),
        child: Column(
          crossAxisAlignment:
              msg.isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            /// 消息内容
            Text(
              msg.text,
              style: GoogleFonts.inter(fontSize: 14, color: textColor),
            ),

            /// 时间戳
            if (msg.timestamp != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  _formatTime(msg.timestamp),
                  style: GoogleFonts.inter(fontSize: 11, color: timeColor),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
