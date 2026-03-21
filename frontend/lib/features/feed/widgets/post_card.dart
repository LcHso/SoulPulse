import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:timeago/timeago.dart' as timeago;
import '../../../core/widgets/image_viewer.dart';
import 'heart_animation.dart';

class PostCard extends StatefulWidget {
  final Map<String, dynamic> post;
  final VoidCallback onLike;
  final VoidCallback? onSave;
  final VoidCallback onDM;
  final VoidCallback? onProfileTap;
  final VoidCallback? onComment;

  const PostCard({
    super.key,
    required this.post,
    required this.onLike,
    this.onSave,
    required this.onDM,
    this.onProfileTap,
    this.onComment,
  });

  @override
  State<PostCard> createState() => _PostCardState();
}

class _PostCardState extends State<PostCard> {
  bool _showHeart = false;

  void _handleDoubleTap() {
    if (widget.post['is_liked'] != true) {
      widget.onLike();
    }
    setState(() => _showHeart = true);
    HapticFeedback.lightImpact();
    Future.delayed(const Duration(milliseconds: 800), () {
      if (mounted) setState(() => _showHeart = false);
    });
  }

  String _formatTime(String? isoString) {
    if (isoString == null || isoString.isEmpty) return '';
    try {
      return timeago.format(DateTime.parse(isoString).toLocal());
    } catch (_) {
      return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    final post = widget.post;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final isLiked = post['is_liked'] == true;
    final isSaved = post['is_saved'] == true;
    final likeCount = (post['like_count'] as int?) ?? 0;
    final commentCount = (post['comment_count'] as int?) ?? 0;
    final avatarUrl = post['ai_avatar'] as String? ?? '';
    final mediaUrl = post['media_url'] as String? ?? '';
    final createdAt = post['created_at'] as String?;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Header: avatar + name
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: GestureDetector(
            onTap: widget.onProfileTap,
            child: Row(
              children: [
                _buildAvatar(avatarUrl, post['ai_name'] as String? ?? 'A', 16),
                const SizedBox(width: 10),
                Text(
                  post['ai_name'] ?? 'AI',
                  style: GoogleFonts.inter(
                      fontWeight: FontWeight.w600, fontSize: 14),
                ),
              ],
            ),
          ),
        ),

        // Image area with double-tap heart, single tap for fullscreen
        GestureDetector(
          onDoubleTap: _handleDoubleTap,
          onTap: () {
            if (mediaUrl.isNotEmpty) {
              ImageViewer.show(context, mediaUrl,
                  heroTag: 'post_${post['id']}');
            }
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
                          placeholder: (context, url) => Center(
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.grey[400],
                            ),
                          ),
                          errorWidget: (context, url, error) => Center(
                            child: Icon(Icons.broken_image_outlined,
                                size: 48, color: Colors.grey[400]),
                          ),
                        )
                      : Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.camera_alt_outlined,
                                  size: 48, color: Colors.grey[500]),
                              const SizedBox(height: 8),
                              Padding(
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 24),
                                child: Text(
                                  post['caption'] ?? '',
                                  textAlign: TextAlign.center,
                                  maxLines: 4,
                                  overflow: TextOverflow.ellipsis,
                                  style: GoogleFonts.inter(
                                      fontSize: 16, color: Colors.grey[500]),
                                ),
                              ),
                            ],
                          ),
                        ),
                ),
              ),
              if (_showHeart) const HeartAnimation(),
            ],
          ),
        ),

        // Action bar: like, comment, DM, save
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            children: [
              GestureDetector(
                onTap: () {
                  widget.onLike();
                  HapticFeedback.lightImpact();
                },
                child: Icon(
                  isLiked ? Icons.favorite : Icons.favorite_border,
                  color: isLiked ? const Color(0xFFED4956) : null,
                  size: 28,
                ),
              ),
              const SizedBox(width: 16),
              GestureDetector(
                onTap: widget.onComment,
                child: const Icon(Icons.chat_bubble_outline, size: 26),
              ),
              const SizedBox(width: 16),
              GestureDetector(
                onTap: widget.onDM,
                child: const Icon(Icons.send_outlined, size: 26),
              ),
              const Spacer(),
              if (widget.onSave != null)
                GestureDetector(
                  onTap: () {
                    widget.onSave!();
                    HapticFeedback.lightImpact();
                  },
                  child: Icon(
                    isSaved ? Icons.bookmark : Icons.bookmark_border,
                    color:
                        isSaved ? Theme.of(context).colorScheme.primary : null,
                    size: 28,
                  ),
                ),
            ],
          ),
        ),

        // Like count
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Text(
            '$likeCount likes',
            style: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 13),
          ),
        ),

        // Caption
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
                  text: '${post['ai_name'] ?? 'AI'} ',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                TextSpan(text: post['caption'] ?? ''),
              ],
            ),
          ),
        ),

        // Comment count
        if (commentCount > 0)
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 2, 14, 0),
            child: GestureDetector(
              onTap: widget.onComment,
              child: Text(
                'View all $commentCount comments',
                style: GoogleFonts.inter(fontSize: 13, color: Colors.grey[500]),
              ),
            ),
          ),

        // Timestamp
        if (createdAt != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 4, 14, 8),
            child: Text(
              _formatTime(createdAt),
              style: GoogleFonts.inter(fontSize: 11, color: Colors.grey[500]),
            ),
          ),

        Divider(height: 1, color: Colors.grey.withValues(alpha: 0.15)),
      ],
    );
  }

  Widget _buildAvatar(String url, String name, double radius) {
    if (url.isNotEmpty) {
      return CircleAvatar(
        radius: radius,
        backgroundColor: Colors.grey[300],
        child: ClipOval(
          child: CachedNetworkImage(
            imageUrl: url,
            width: radius * 2,
            height: radius * 2,
            fit: BoxFit.cover,
            errorWidget: (_, __, ___) => Text(
              name.isNotEmpty ? name[0] : 'A',
              style: GoogleFonts.inter(
                  fontWeight: FontWeight.w600, color: Colors.grey[700]),
            ),
          ),
        ),
      );
    }
    return CircleAvatar(
      radius: radius,
      backgroundColor: Colors.grey[300],
      child: Text(
        name.isNotEmpty ? name[0] : 'A',
        style: GoogleFonts.inter(
            fontWeight: FontWeight.w600, color: Colors.grey[700]),
      ),
    );
  }
}
