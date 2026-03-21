import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/api/api_client.dart';
import '../../core/api/ws_client.dart';

class ChatPage extends StatefulWidget {
  final int aiId;
  final String aiName;
  final String? postContext;

  const ChatPage({
    super.key,
    required this.aiId,
    required this.aiName,
    this.postContext,
  });

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> with TickerProviderStateMixin {
  final _messageCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final List<_ChatMsg> _messages = [];

  WsClient? _wsClient;
  StreamSubscription? _wsSub;
  WsConnectionStatus _connectionStatus = WsConnectionStatus.disconnected;

  bool _sending = false;
  bool _loadingHistory = false;
  bool _hasMoreHistory = true;
  int? _oldestMessageId;

  // Emotion status
  String? _emotionMood;

  // Typing animation
  late AnimationController _typingAnimCtrl;

  @override
  void initState() {
    super.initState();
    _scrollCtrl.addListener(_onScroll);
    _typingAnimCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
    _loadHistory();
    _connectWebSocket();
    _loadEmotionStatus();
  }

  @override
  void dispose() {
    // Mark conversation as read when leaving
    ApiClient.post('/api/chat/mark-read/${widget.aiId}', {})
        .catchError((_) => <String, dynamic>{});
    _scrollCtrl.removeListener(_onScroll);
    _scrollCtrl.dispose();
    _messageCtrl.dispose();
    _typingAnimCtrl.dispose();
    _wsSub?.cancel();
    _wsClient?.dispose();
    super.dispose();
  }

  // -- Emotion status -------------------------------------------------------

  Future<void> _loadEmotionStatus() async {
    try {
      final data = await ApiClient.get('/api/ai/emotion/${widget.aiId}');
      if (mounted) {
        setState(() {
          _emotionMood = data['mood'] as String?;
        });
      }
    } catch (_) {}
  }

  // -- History loading -------------------------------------------------------

  Future<void> _loadHistory({int? beforeId}) async {
    if (_loadingHistory) return;
    if (beforeId == null && !_hasMoreHistory) return;

    setState(() => _loadingHistory = true);

    try {
      String path = '/api/chat/history/${widget.aiId}?limit=30';
      if (beforeId != null) path += '&before_id=$beforeId';

      final result = await ApiClient.get(path, useCache: false);
      final List<dynamic> messagesJson = result['messages'] ?? [];
      final hasMore = result['has_more'] ?? false;

      final newMessages =
          messagesJson.map((m) => _ChatMsg.fromJson(m)).toList();

      if (mounted) {
        setState(() {
          if (beforeId != null) {
            _messages.insertAll(0, newMessages);
          } else {
            _messages.clear();
            if (widget.postContext != null && widget.postContext!.isNotEmpty) {
              _messages.add(_ChatMsg(
                text: 'Regarding post: "${widget.postContext}"',
                isUser: false,
                isContext: true,
              ));
            }
            _messages.addAll(newMessages);
          }
          _hasMoreHistory = hasMore;
          if (newMessages.isNotEmpty) {
            _oldestMessageId = newMessages.first.id;
          }
          _loadingHistory = false;
        });
        if (beforeId == null) _scrollToBottom();
      }
    } catch (e) {
      if (mounted) setState(() => _loadingHistory = false);
    }
  }

  void _onScroll() {
    if (_scrollCtrl.position.pixels < 100 &&
        _hasMoreHistory &&
        !_loadingHistory &&
        _oldestMessageId != null) {
      _loadHistory(beforeId: _oldestMessageId);
    }
  }

  // -- WebSocket connection -------------------------------------------------

  void _connectWebSocket() {
    _wsClient = WsClient(
      aiId: widget.aiId,
      onStatusChange: (status) {
        if (mounted) setState(() => _connectionStatus = status);
      },
    );
    _wsSub = _wsClient!.messages.listen(_onWsMessage);
    _wsClient!.connect();
  }

  void _onWsMessage(Map<String, dynamic> msg) {
    final type = msg['type'] as String?;
    final data = msg['data'] as Map<String, dynamic>? ?? {};

    switch (type) {
      case WsMessageType.aiReply:
        _onAiReply(data);
        break;
      case WsMessageType.proactiveDm:
        _onProactiveDm(data);
        break;
      case WsMessageType.messageSaved:
        break;
      case WsMessageType.error:
        _onWsError(data);
        break;
    }
  }

  void _onAiReply(Map<String, dynamic> data) {
    final text = data['text'] as String? ?? '';
    final messageId = data['message_id'] as int?;
    final timestamp = data['created_at'] as String?;

    setState(() {
      _sending = false;
      _messages.add(_ChatMsg(
        id: messageId,
        text: text,
        isUser: false,
        timestamp: timestamp ?? DateTime.now().toIso8601String(),
      ));
    });
    _scrollToBottom();
  }

  void _onProactiveDm(Map<String, dynamic> data) {
    final text = data['text'] as String? ?? '';
    final messageId = data['message_id'] as int?;
    final event = data['event'] as String?;

    setState(() {
      _messages.add(_ChatMsg(
        id: messageId,
        text: text,
        isUser: false,
        messageType: 'proactive_dm',
        event: event,
        timestamp: DateTime.now().toIso8601String(),
      ));
    });
    _scrollToBottom();
  }

  void _onWsError(Map<String, dynamic> data) {
    final detail = data['detail'] as String? ?? 'Unknown error';
    if (_sending) {
      setState(() {
        _sending = false;
        _messages.add(_ChatMsg(
          text: 'Failed to send: $detail',
          isUser: false,
          isError: true,
        ));
      });
    }
  }

  // -- Send message ---------------------------------------------------------

  Future<void> _send() async {
    final text = _messageCtrl.text.trim();
    if (text.isEmpty) return;

    setState(() {
      _messages.add(_ChatMsg(
        text: text,
        isUser: true,
        timestamp: DateTime.now().toIso8601String(),
      ));
      _messageCtrl.clear();
      _sending = true;
    });
    _scrollToBottom();

    if (_connectionStatus == WsConnectionStatus.connected &&
        _wsClient != null) {
      _wsClient!.sendMessage(text, postContext: widget.postContext);
    } else {
      await _sendViaRest(text);
    }
  }

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
          _messages.add(_ChatMsg(
            text: 'Failed to get reply. Please try again.',
            isUser: false,
            isError: true,
          ));
        });
      }
    }
  }

  // -- Delete message -------------------------------------------------------

  Future<void> _deleteMessage(int index) async {
    final msg = _messages[index];
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

  void _showMessageMenu(int index) {
    final msg = _messages[index];
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
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

  // -- UI -------------------------------------------------------------------

  String get _statusText {
    switch (_connectionStatus) {
      case WsConnectionStatus.connected:
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

  Color get _statusColor {
    switch (_connectionStatus) {
      case WsConnectionStatus.connected:
        return _moodColor(_emotionMood);
      case WsConnectionStatus.connecting:
      case WsConnectionStatus.reconnecting:
        return Colors.orange;
      case WsConnectionStatus.disconnected:
        return Colors.grey;
    }
  }

  Color _moodColor(String? mood) {
    switch (mood) {
      case 'joyful':
        return Colors.amber;
      case 'good':
        return Colors.green;
      case 'neutral':
        return Colors.blue;
      case 'subdued':
        return Colors.orange;
      case 'melancholic':
        return Colors.indigo;
      default:
        return Colors.green;
    }
  }

  bool _shouldShowDateSeparator(int index) {
    if (index == 0) return true;
    final current = _messages[index].timestamp;
    final prev = _messages[index - 1].timestamp;
    if (current == null || prev == null) return false;
    try {
      final currentDate = DateTime.parse(current).toLocal();
      final prevDate = DateTime.parse(prev).toLocal();
      return currentDate.day != prevDate.day ||
          currentDate.month != prevDate.month ||
          currentDate.year != prevDate.year;
    } catch (_) {
      return false;
    }
  }

  String _formatDateSeparator(String? isoString) {
    if (isoString == null) return '';
    try {
      final dt = DateTime.parse(isoString).toLocal();
      final now = DateTime.now();
      if (dt.year == now.year && dt.month == now.month && dt.day == now.day) {
        return 'Today';
      }
      final yesterday = now.subtract(const Duration(days: 1));
      if (dt.year == yesterday.year &&
          dt.month == yesterday.month &&
          dt.day == yesterday.day) {
        return 'Yesterday';
      }
      return '${dt.month}/${dt.day}/${dt.year}';
    } catch (_) {
      return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.pop(),
        ),
        title: GestureDetector(
          onTap: () {
            final aiName = Uri.encodeComponent(widget.aiName);
            context.push('/ai/${widget.aiId}?name=$aiName');
          },
          child: Row(
            children: [
              CircleAvatar(
                radius: 16,
                backgroundColor: Colors.grey[300],
                child: Text(
                  widget.aiName[0],
                  style: GoogleFonts.inter(
                      fontWeight: FontWeight.w600, color: Colors.grey[700]),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.aiName,
                      style: GoogleFonts.inter(
                          fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                    Row(
                      children: [
                        Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            color: _statusColor,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 4),
                        Text(
                          _statusText,
                          style: GoogleFonts.inter(
                              fontSize: 11, color: _statusColor),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      body: Column(
        children: [
          // Loading indicator at top for pagination
          if (_loadingHistory)
            const Padding(
              padding: EdgeInsets.all(8),
              child: SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2)),
            ),

          // Messages
          Expanded(
            child: _messages.isEmpty && !_loadingHistory
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
                          if (showDate)
                            Padding(
                              padding: const EdgeInsets.symmetric(vertical: 12),
                              child: Text(
                                _formatDateSeparator(msg.timestamp),
                                style: GoogleFonts.inter(
                                    fontSize: 12, color: Colors.grey[500]),
                              ),
                            ),
                          GestureDetector(
                            onLongPress: () => _showMessageMenu(index),
                            child: _MessageBubble(msg: msg, isDark: isDark),
                          ),
                        ],
                      );
                    },
                  ),
          ),

          // Typing indicator
          if (_sending)
            Padding(
              padding: const EdgeInsets.only(left: 20, bottom: 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: _TypingIndicator(
                  animationController: _typingAnimCtrl,
                  aiName: widget.aiName,
                ),
              ),
            ),

          // Input bar
          Container(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF121212) : Colors.white,
              border: Border(
                top: BorderSide(color: Colors.grey.withValues(alpha: 0.2)),
              ),
            ),
            child: SafeArea(
              top: false,
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _messageCtrl,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _send(),
                      decoration: InputDecoration(
                        hintText: 'Message...',
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(24),
                          borderSide: BorderSide.none,
                        ),
                        filled: true,
                        fillColor: isDark
                            ? const Color(0xFF262626)
                            : const Color(0xFFEFEFEF),
                        contentPadding: const EdgeInsets.symmetric(
                            horizontal: 20, vertical: 10),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  GestureDetector(
                    onTap: _sending ? null : _send,
                    child: Container(
                      padding: const EdgeInsets.all(10),
                      decoration: const BoxDecoration(
                        color: Color(0xFF0095F6),
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

// -- Typing indicator with animated dots ------------------------------------

class _TypingIndicator extends StatelessWidget {
  final AnimationController animationController;
  final String aiName;

  const _TypingIndicator(
      {required this.animationController, required this.aiName});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '$aiName ',
          style: GoogleFonts.inter(
              fontSize: 12, color: Colors.grey, fontStyle: FontStyle.italic),
        ),
        AnimatedBuilder(
          animation: animationController,
          builder: (context, child) {
            final progress = animationController.value;
            return Row(
              mainAxisSize: MainAxisSize.min,
              children: List.generate(3, (i) {
                final delay = i * 0.2;
                final opacity = ((progress - delay) % 1.0).clamp(0.0, 1.0);
                final scale = 0.5 + (opacity > 0.5 ? 1.0 - opacity : opacity);
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 1),
                  child: Transform.scale(
                    scale: scale,
                    child: Container(
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(
                        color:
                            Colors.grey.withValues(alpha: 0.4 + opacity * 0.6),
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

// -- Chat message model -----------------------------------------------------

class _ChatMsg {
  final int? id;
  final String text;
  final bool isUser;
  final bool isContext;
  final bool isError;
  final String messageType;
  final String? event;
  final String? timestamp;

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

// -- Message bubble widget --------------------------------------------------

class _MessageBubble extends StatelessWidget {
  final _ChatMsg msg;
  final bool isDark;

  const _MessageBubble({required this.msg, required this.isDark});

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
    // Context bubble
    if (msg.isContext) {
      return Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF1A2A1A) : const Color(0xFFE8F5E9),
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

    // Proactive DM bubble
    if (msg.messageType == 'proactive_dm') {
      return Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF2A1A2A) : const Color(0xFFFCE4EC),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isDark ? Colors.pink[800]! : Colors.pink[200]!,
            width: 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
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
            Text(
              msg.text,
              style: GoogleFonts.inter(
                  fontSize: 14, color: isDark ? Colors.white : Colors.black87),
            ),
            if (msg.timestamp != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  _formatTime(msg.timestamp),
                  style:
                      GoogleFonts.inter(fontSize: 10, color: Colors.grey[500]),
                ),
              ),
          ],
        ),
      );
    }

    // Regular message bubble
    final bgColor = msg.isUser
        ? const Color(0xFF0095F6)
        : msg.isError
            ? Colors.red.withValues(alpha: 0.15)
            : (isDark ? const Color(0xFF262626) : const Color(0xFFEFEFEF));

    final textColor = msg.isUser
        ? Colors.white
        : msg.isError
            ? Colors.red
            : (isDark ? Colors.white : Colors.black);

    final timeColor = msg.isUser ? Colors.white70 : Colors.grey[500];

    return Align(
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
            bottomLeft: Radius.circular(msg.isUser ? 18 : 4),
            bottomRight: Radius.circular(msg.isUser ? 4 : 18),
          ),
        ),
        child: Column(
          crossAxisAlignment:
              msg.isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            Text(
              msg.text,
              style: GoogleFonts.inter(fontSize: 14, color: textColor),
            ),
            if (msg.timestamp != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  _formatTime(msg.timestamp),
                  style: GoogleFonts.inter(fontSize: 10, color: timeColor),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
