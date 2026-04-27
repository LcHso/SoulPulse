import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:timeago/timeago.dart' as timeago;
import '../../core/api/api_client.dart';
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
  bool _saved = false;
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
    _liked = widget.post['is_liked'] == true;
    _saved = widget.post['is_saved'] == true;
    _loadComments();
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
      final comments = await ApiClient.getList(
          '/api/feed/posts/$_postId/comments',
          useCache: false);
      if (mounted) {
        setState(() {
          _comments = _sortCommentsWithReplies(comments);
          _loadingComments = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loadingComments = false);
    }
  }

  /// Sort comments so that AI replies appear directly after their parent comment.
  List<dynamic> _sortCommentsWithReplies(List<dynamic> comments) {
    final roots = <Map<String, dynamic>>[];
    final replyMap = <int, List<Map<String, dynamic>>>{};

    for (final c in comments) {
      final comment = c as Map<String, dynamic>;
      final replyTo = comment['reply_to'] as int?;
      if (replyTo != null) {
        replyMap.putIfAbsent(replyTo, () => []).add(comment);
      } else {
        roots.add(comment);
      }
    }

    final sorted = <Map<String, dynamic>>[];
    for (final root in roots) {
      sorted.add(root);
      final replies = replyMap[root['id'] as int?] ?? [];
      sorted.addAll(replies);
    }

    // Add any orphaned replies (parent not in current page)
    for (final entry in replyMap.entries) {
      if (!roots.any((r) => r['id'] == entry.key)) {
        sorted.addAll(entry.value);
      }
    }

    return sorted;
  }

  Future<void> _submitComment() async {
    final text = _commentController.text.trim();
    if (text.isEmpty) return;

    setState(() => _submitting = true);
    try {
      final newComment = await ApiClient.post(
          '/api/feed/posts/$_postId/comments', {'content': text});
      _commentController.clear();
      // Optimistically add the new comment immediately
      if (mounted) {
        setState(() {
          _comments = _sortCommentsWithReplies([..._comments, newComment]);
        });
      }
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
    final wasLiked = _liked;
    setState(() {
      _showHeart = true;
      _liked = !wasLiked;
      _likeCount += wasLiked ? -1 : 1;
    });
    HapticFeedback.lightImpact();
    Future.delayed(const Duration(milliseconds: 800), () {
      if (mounted) setState(() => _showHeart = false);
    });
    try {
      if (wasLiked) {
        await ApiClient.delete('/api/feed/posts/$_postId/like');
      } else {
        await ApiClient.post('/api/feed/posts/$_postId/like', {});
      }
    } catch (_) {
      // Revert
      setState(() {
        _liked = wasLiked;
        _likeCount += wasLiked ? 1 : -1;
      });
    }
  }

  Future<void> _handleSave() async {
    final wasSaved = _saved;
    setState(() => _saved = !wasSaved);
    HapticFeedback.lightImpact();
    try {
      if (wasSaved) {
        await ApiClient.delete('/api/feed/posts/$_postId/save');
      } else {
        await ApiClient.post('/api/feed/posts/$_postId/save', {});
      }
    } catch (_) {
      setState(() => _saved = wasSaved);
    }
  }

  void _openChat() {
    final aiId = widget.post['ai_id'] as int? ?? 1;
    final aiName = Uri.encodeComponent(widget.aiName);
    final caption = widget.post['caption'] as String?;
    var path = '/chat/$aiId?name=$aiName';
    if (caption != null && caption.isNotEmpty) {
      path += '&context=${Uri.encodeComponent(caption)}';
    }
    context.push(path);
  }

  void _openProfile() {
    final aiId = widget.post['ai_id'] as int? ?? 1;
    final aiName = Uri.encodeComponent(widget.aiName);
    context.push('/ai/$aiId?name=$aiName');
  }

  String _formatTime(String? isoString) {
    if (isoString == null || isoString.isEmpty) return '';
    try {
      final dt = DateTime.parse(isoString).toLocal();
      return timeago.format(dt);
    } catch (_) {
      return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final mediaUrl =
        ApiClient.proxyImageUrl(widget.post['media_url'] as String? ?? '');
    final caption = widget.post['caption'] as String? ?? '';
    final createdAt = widget.post['created_at'] as String?;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.pop(),
        ),
        title: Text('Post',
            style:
                GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 18)),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView(
              children: [
                // Header
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  child: GestureDetector(
                    onTap: _openProfile,
                    child: Row(
                      children: [
                        _buildAvatar(ApiClient.proxyImageUrl(widget.aiAvatar),
                            widget.aiName, 16),
                        const SizedBox(width: 10),
                        Text(widget.aiName,
                            style: GoogleFonts.inter(
                                fontWeight: FontWeight.w600, fontSize: 14)),
                      ],
                    ),
                  ),
                ),

                // Image with double-tap
                GestureDetector(
                  onDoubleTap: () {
                    if (!_liked) _handleLike();
                    setState(() => _showHeart = true);
                    Future.delayed(const Duration(milliseconds: 800), () {
                      if (mounted) setState(() => _showHeart = false);
                    });
                  },
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
                              ? CachedNetworkImage(
                                  imageUrl: mediaUrl,
                                  fit: BoxFit.cover,
                                  placeholder: (_, __) => Center(
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: Colors.grey[400]),
                                  ),
                                  errorWidget: (_, __, ___) => Center(
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
                        onTap: _handleLike,
                        child: Icon(
                          _liked ? Icons.favorite : Icons.favorite_border,
                          color: _liked ? const Color(0xFFED4956) : null,
                          size: 28,
                        ),
                      ),
                      const SizedBox(width: 16),
                      const Icon(Icons.chat_bubble_outline, size: 26),
                      const SizedBox(width: 16),
                      GestureDetector(
                        onTap: _openChat,
                        child: const Icon(Icons.send_outlined, size: 26),
                      ),
                      const Spacer(),
                      GestureDetector(
                        onTap: _handleSave,
                        child: Icon(
                          _saved ? Icons.bookmark : Icons.bookmark_border,
                          color: _saved
                              ? Theme.of(context).colorScheme.primary
                              : null,
                          size: 28,
                        ),
                      ),
                    ],
                  ),
                ),

                // Like count
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14),
                  child: Text('$_likeCount likes',
                      style: GoogleFonts.inter(
                          fontWeight: FontWeight.w600, fontSize: 13)),
                ),

                // Caption
                if (caption.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(14, 4, 14, 4),
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

                // Timestamp
                if (createdAt != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(14, 4, 14, 8),
                    child: Text(
                      _formatTime(createdAt),
                      style: GoogleFonts.inter(
                          fontSize: 11, color: Colors.grey[500]),
                    ),
                  ),

                const Divider(height: 1),

                // Comments header
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
                  child: Text('Comments',
                      style: GoogleFonts.inter(
                          fontWeight: FontWeight.w600, fontSize: 14)),
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
                      child: Text('No comments yet. Be the first!',
                          style: GoogleFonts.inter(
                              fontSize: 13, color: Colors.grey[500])),
                    ),
                  )
                else
                  ..._comments.map((c) {
                    final comment = c as Map<String, dynamic>;
                    final isAi = comment['is_ai_reply'] == true;
                    final authorName = comment['author_name'] as String? ?? '';
                    final authorAvatar = ApiClient.proxyImageUrl(
                        comment['author_avatar'] as String? ?? '');
                    final content = comment['content'] as String? ?? '';
                    final commentCreatedAt =
                        comment['created_at'] as String? ?? '';
                    final replyTo = comment['reply_to'];

                    return Padding(
                      padding: EdgeInsets.fromLTRB(
                          replyTo != null ? 40 : 14, 6, 14, 6),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _buildAvatar(
                            authorAvatar,
                            authorName,
                            14,
                            fallbackColor: isAi
                                ? const Color(0xFFDD2A7B)
                                : Colors.grey[400]!,
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
                                  _formatTime(commentCreatedAt),
                                  style: GoogleFonts.inter(
                                      fontSize: 11, color: Colors.grey[500]),
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

          // Comment input bar
          Container(
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF1C1C1E) : Colors.white,
              border: Border(
                top: BorderSide(
                    color: isDark ? Colors.white12 : Colors.grey[300]!),
              ),
            ),
            padding: EdgeInsets.fromLTRB(
                14, 8, 8, MediaQuery.of(context).padding.bottom + 8),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _commentController,
                    style: GoogleFonts.inter(fontSize: 14),
                    decoration: InputDecoration(
                      hintText: 'Add a comment...',
                      hintStyle: GoogleFonts.inter(
                          fontSize: 14, color: Colors.grey[500]),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(20),
                        borderSide: BorderSide.none,
                      ),
                      filled: true,
                      fillColor: isDark
                          ? Colors.white.withValues(alpha: 0.08)
                          : Colors.grey[100],
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 10),
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

  Widget _buildAvatar(String url, String name, double radius,
      {Color? fallbackColor}) {
    final bgColor = fallbackColor ?? Colors.grey[300]!;
    if (url.isNotEmpty) {
      return CircleAvatar(
        radius: radius,
        backgroundColor: bgColor,
        child: ClipOval(
          child: CachedNetworkImage(
            imageUrl: url,
            width: radius * 2,
            height: radius * 2,
            fit: BoxFit.cover,
            errorWidget: (_, __, ___) => Text(
              name.isNotEmpty ? name[0] : 'A',
              style: GoogleFonts.inter(
                  fontWeight: FontWeight.w600, color: Colors.white),
            ),
          ),
        ),
      );
    }
    return CircleAvatar(
      radius: radius,
      backgroundColor: bgColor,
      child: Text(
        name.isNotEmpty ? name[0] : 'A',
        style:
            GoogleFonts.inter(fontWeight: FontWeight.w600, color: Colors.white),
      ),
    );
  }
}
