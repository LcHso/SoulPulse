import 'dart:async';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/api/api_client.dart';
import '../../core/services/notification_service.dart';
import '../chat/chat_page.dart';
import '../feed/widgets/heart_animation.dart';

class PostDetailPage extends StatefulWidget {
  final Map<String, dynamic> post;
  final String aiName;
  final String aiAvatar;

  const PostDetailPage({
    super.key,
    required this.post,
    required this.aiName,
    required this.aiAvatar,
  });

  @override
  State<PostDetailPage> createState() => _PostDetailPageState();
}

class _PostDetailPageState extends State<PostDetailPage> {
  bool _showHeart = false;
  bool _liked = false;
  late int _likeCount;

  final _commentController = TextEditingController();
  List<dynamic> _comments = [];
  bool _loadingComments = true;
  bool _submitting = false;
  Timer? _pollTimer;

  int get _postId => widget.post['id'] as int? ?? 0;

  @override
  void initState() {
    super.initState();
    _likeCount = widget.post['like_count'] as int? ?? 0;
    _loadComments();
    // Poll for new comments (AI replies) every 30 seconds
    _pollTimer =
        Timer.periodic(const Duration(seconds: 30), (_) => _loadComments());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _commentController.dispose();
    super.dispose();
  }

  Future<void> _loadComments() async {
    try {
      final comments =
          await ApiClient.getList('/api/feed/posts/$_postId/comments');
      if (mounted) {
        final oldCount = _comments.length;
        setState(() {
          _comments = comments;
          _loadingComments = false;
        });
        // If new AI reply appeared, show notification
        if (oldCount > 0 && comments.length > oldCount) {
          final latest = comments.last as Map<String, dynamic>;
          if (latest['is_ai_reply'] == true && mounted) {
            NotificationService.instance.show(
              context,
              title: '${widget.aiName} replied to your comment',
              body: '${latest['content']}',
            );
          }
        }
      }
    } catch (_) {
      if (mounted) setState(() => _loadingComments = false);
    }
  }

  Future<void> _submitComment() async {
    final text = _commentController.text.trim();
    if (text.isEmpty) return;

    setState(() => _submitting = true);
    try {
      await ApiClient.post(
          '/api/feed/posts/$_postId/comments', {'content': text});
      _commentController.clear();
      await _loadComments();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to post comment')),
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _handleLike() async {
    setState(() {
      _showHeart = true;
      _liked = true;
    });
    Future.delayed(const Duration(milliseconds: 800), () {
      if (mounted) setState(() => _showHeart = false);
    });
    try {
      final result =
          await ApiClient.post('/api/feed/posts/${widget.post['id']}/like', {});
      setState(() {
        _likeCount = result['like_count'] as int? ?? _likeCount + 1;
      });
    } catch (_) {}
  }

  void _openChat() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ChatPage(
          aiId: widget.post['ai_id'] as int? ?? 1,
          aiName: widget.aiName,
          postContext: widget.post['caption'] as String?,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final mediaUrl = widget.post['media_url'] as String? ?? '';
    final caption = widget.post['caption'] as String? ?? '';

    return Scaffold(
      appBar: AppBar(
        title: Text(
          'Post',
          style: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 18),
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView(
              children: [
                // Header: avatar + name
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  child: Row(
                    children: [
                      CircleAvatar(
                        radius: 16,
                        backgroundColor: Colors.grey[300],
                        child: Text(
                          widget.aiName.isNotEmpty ? widget.aiName[0] : 'A',
                          style: GoogleFonts.inter(
                            fontWeight: FontWeight.w600,
                            color: Colors.grey[700],
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Text(
                        widget.aiName,
                        style: GoogleFonts.inter(
                          fontWeight: FontWeight.w600,
                          fontSize: 14,
                        ),
                      ),
                    ],
                  ),
                ),

                // Image with double-tap like
                GestureDetector(
                  onDoubleTap: _handleLike,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      AspectRatio(
                        aspectRatio: 4 / 5,
                        child: Container(
                          width: double.infinity,
                          color: isDark
                              ? const Color(0xFF1A1A1A)
                              : const Color(0xFFF0F0F0),
                          child: mediaUrl.isNotEmpty
                              ? Image.network(
                                  ApiClient.proxyImageUrl(mediaUrl),
                                  fit: BoxFit.cover,
                                  loadingBuilder: (context, child, progress) {
                                    if (progress == null) return child;
                                    return Center(
                                      child: CircularProgressIndicator(
                                        value: progress.expectedTotalBytes !=
                                                null
                                            ? progress.cumulativeBytesLoaded /
                                                progress.expectedTotalBytes!
                                            : null,
                                        strokeWidth: 2,
                                        color: Colors.grey[400],
                                      ),
                                    );
                                  },
                                  errorBuilder: (context, error, stack) =>
                                      Center(
                                    child: Icon(Icons.broken_image_outlined,
                                        size: 48, color: Colors.grey[400]),
                                  ),
                                )
                              : Center(
                                  child: Icon(Icons.camera_alt_outlined,
                                      size: 48, color: Colors.grey[500]),
                                ),
                        ),
                      ),
                      if (_showHeart) const HeartAnimation(),
                    ],
                  ),
                ),

                // Action bar
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  child: Row(
                    children: [
                      GestureDetector(
                        onTap: () {
                          setState(() => _liked = !_liked);
                          if (_liked) _handleLike();
                        },
                        child: Icon(
                          _liked ? Icons.favorite : Icons.favorite_border,
                          color: _liked ? const Color(0xFFED4956) : null,
                          size: 28,
                        ),
                      ),
                      const SizedBox(width: 16),
                      GestureDetector(
                        onTap: () =>
                            FocusScope.of(context).requestFocus(FocusNode()),
                        child: const Icon(Icons.chat_bubble_outline, size: 26),
                      ),
                      const SizedBox(width: 16),
                      GestureDetector(
                        onTap: _openChat,
                        child: const Icon(Icons.send_outlined, size: 26),
                      ),
                    ],
                  ),
                ),

                // Like count
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14),
                  child: Text(
                    '$_likeCount likes',
                    style: GoogleFonts.inter(
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                    ),
                  ),
                ),

                // Caption
                if (caption.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(14, 4, 14, 8),
                    child: RichText(
                      text: TextSpan(
                        style: GoogleFonts.inter(
                          fontSize: 13,
                          color: isDark ? Colors.white : Colors.black,
                        ),
                        children: [
                          TextSpan(
                            text: '${widget.aiName} ',
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          TextSpan(text: caption),
                        ],
                      ),
                    ),
                  ),

                // Created at
                if (widget.post['created_at'] != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(14, 0, 14, 8),
                    child: Text(
                      _formatTime(widget.post['created_at'] as String),
                      style: GoogleFonts.inter(
                        fontSize: 11,
                        color: Colors.grey[500],
                      ),
                    ),
                  ),

                // Divider before comments
                const Divider(height: 1),

                // Comment section header
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
                  child: Text(
                    'Comments',
                    style: GoogleFonts.inter(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                  ),
                ),

                // Comments list
                if (_loadingComments)
                  const Padding(
                    padding: EdgeInsets.all(20),
                    child: Center(
                        child: CircularProgressIndicator(strokeWidth: 2)),
                  )
                else if (_comments.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(20),
                    child: Center(
                      child: Text(
                        'No comments yet. Be the first!',
                        style: GoogleFonts.inter(
                          fontSize: 13,
                          color: Colors.grey[500],
                        ),
                      ),
                    ),
                  )
                else
                  ..._comments.map((c) {
                    final comment = c as Map<String, dynamic>;
                    final isAi = comment['is_ai_reply'] == true;
                    final authorName = comment['author_name'] as String? ?? '';
                    final content = comment['content'] as String? ?? '';
                    final createdAt = comment['created_at'] as String? ?? '';
                    final replyTo = comment['reply_to'];

                    return Padding(
                      padding: EdgeInsets.fromLTRB(
                        replyTo != null ? 40 : 14,
                        6,
                        14,
                        6,
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          CircleAvatar(
                            radius: 14,
                            backgroundColor: isAi
                                ? const Color(0xFFDD2A7B)
                                : Colors.grey[400],
                            child: Text(
                              authorName.isNotEmpty ? authorName[0] : '?',
                              style: GoogleFonts.inter(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: Colors.white,
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                RichText(
                                  text: TextSpan(
                                    style: GoogleFonts.inter(
                                      fontSize: 13,
                                      color:
                                          isDark ? Colors.white : Colors.black,
                                    ),
                                    children: [
                                      TextSpan(
                                        text: '$authorName ',
                                        style: TextStyle(
                                          fontWeight: FontWeight.w600,
                                          color: isAi
                                              ? const Color(0xFFDD2A7B)
                                              : null,
                                        ),
                                      ),
                                      TextSpan(text: content),
                                    ],
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  _formatTime(createdAt),
                                  style: GoogleFonts.inter(
                                    fontSize: 11,
                                    color: Colors.grey[500],
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    );
                  }),

                const SizedBox(height: 80),
              ],
            ),
          ),

          // Comment input bar (fixed at bottom)
          Container(
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF1C1C1E) : Colors.white,
              border: Border(
                top: BorderSide(
                  color: isDark ? Colors.white12 : Colors.grey[300]!,
                ),
              ),
            ),
            padding: EdgeInsets.fromLTRB(
              14,
              8,
              8,
              MediaQuery.of(context).padding.bottom + 8,
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _commentController,
                    style: GoogleFonts.inter(fontSize: 14),
                    decoration: InputDecoration(
                      hintText: 'Add a comment...',
                      hintStyle: GoogleFonts.inter(
                        fontSize: 14,
                        color: Colors.grey[500],
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(20),
                        borderSide: BorderSide.none,
                      ),
                      filled: true,
                      fillColor: isDark
                          ? Colors.white.withValues(alpha: 0.08)
                          : Colors.grey[100],
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 10,
                      ),
                    ),
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _submitComment(),
                  ),
                ),
                const SizedBox(width: 6),
                _submitting
                    ? const SizedBox(
                        width: 36,
                        height: 36,
                        child: Padding(
                          padding: EdgeInsets.all(8),
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      )
                    : IconButton(
                        icon: const Icon(Icons.arrow_upward_rounded),
                        style: IconButton.styleFrom(
                          backgroundColor: const Color(0xFF3897F0),
                          foregroundColor: Colors.white,
                        ),
                        onPressed: _submitComment,
                      ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _formatTime(String isoString) {
    try {
      final dt = DateTime.parse(isoString);
      final now = DateTime.now();
      final diff = now.difference(dt);
      if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
      if (diff.inHours < 24) return '${diff.inHours}h ago';
      if (diff.inDays < 7) return '${diff.inDays}d ago';
      return '${dt.month}/${dt.day}/${dt.year}';
    } catch (_) {
      return '';
    }
  }
}
