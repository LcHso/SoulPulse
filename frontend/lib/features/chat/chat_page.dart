import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/api/api_client.dart';

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

class _ChatPageState extends State<ChatPage> {
  final _messageCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final List<_ChatMsg> _messages = [];
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    // If we came from a post, show context bubble
    if (widget.postContext != null && widget.postContext!.isNotEmpty) {
      _messages.add(_ChatMsg(
        text: 'Regarding post: "${widget.postContext}"',
        isUser: false,
        isContext: true,
      ));
    }
  }

  Future<void> _send() async {
    final text = _messageCtrl.text.trim();
    if (text.isEmpty) return;

    setState(() {
      _messages.add(_ChatMsg(text: text, isUser: true));
      _messageCtrl.clear();
      _sending = true;
    });
    _scrollToBottom();

    try {
      final result = await ApiClient.post('/api/chat/send', {
        'ai_id': widget.aiId,
        'message': text,
        if (widget.postContext != null) 'post_context': widget.postContext,
      });
      setState(() {
        _messages.add(_ChatMsg(
          text: result['reply'] ?? '...',
          isUser: false,
        ));
      });
    } catch (e) {
      setState(() {
        _messages.add(_ChatMsg(
          text: 'Failed to get reply. Please try again.',
          isUser: false,
          isError: true,
        ));
      });
    } finally {
      if (mounted) setState(() => _sending = false);
      _scrollToBottom();
    }
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

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            CircleAvatar(
              radius: 16,
              backgroundColor: Colors.grey[300],
              child: Text(
                widget.aiName[0],
                style: GoogleFonts.inter(
                  fontWeight: FontWeight.w600,
                  color: Colors.grey[700],
                ),
              ),
            ),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  widget.aiName,
                  style: GoogleFonts.inter(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  'Active now',
                  style: GoogleFonts.inter(
                    fontSize: 12,
                    color: Colors.green,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          // Messages
          Expanded(
            child: ListView.builder(
              controller: _scrollCtrl,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final msg = _messages[index];
                return _MessageBubble(msg: msg, isDark: isDark);
              },
            ),
          ),

          // Typing indicator
          if (_sending)
            Padding(
              padding: const EdgeInsets.only(left: 20, bottom: 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  '${widget.aiName} is typing...',
                  style: GoogleFonts.inter(
                    fontSize: 12,
                    color: Colors.grey,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ),
            ),

          // Input bar
          Container(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF121212) : Colors.white,
              border: Border(
                top: BorderSide(
                  color: Colors.grey.withValues(alpha: 0.2),
                ),
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
                      child: const Icon(Icons.send, color: Colors.white, size: 20),
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

class _ChatMsg {
  final String text;
  final bool isUser;
  final bool isContext;
  final bool isError;

  _ChatMsg({
    required this.text,
    required this.isUser,
    this.isContext = false,
    this.isError = false,
  });
}

class _MessageBubble extends StatelessWidget {
  final _ChatMsg msg;
  final bool isDark;

  const _MessageBubble({required this.msg, required this.isDark});

  @override
  Widget build(BuildContext context) {
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
        child: Text(
          msg.text,
          style: GoogleFonts.inter(fontSize: 14, color: textColor),
        ),
      ),
    );
  }
}
