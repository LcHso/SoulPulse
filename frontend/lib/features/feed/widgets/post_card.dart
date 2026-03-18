import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'heart_animation.dart';
import '../../../core/api/api_client.dart';

class PostCard extends StatefulWidget {
  final Map<String, dynamic> post;
  final VoidCallback onDoubleTap;
  final VoidCallback onDM;
  final VoidCallback? onProfileTap;
  final VoidCallback? onComment;

  const PostCard({
    super.key,
    required this.post,
    required this.onDoubleTap,
    required this.onDM,
    this.onProfileTap,
    this.onComment,
  });

  @override
  State<PostCard> createState() => _PostCardState();
}

class _PostCardState extends State<PostCard> {
  bool _showHeart = false;
  bool _liked = false;

  void _handleDoubleTap() {
    setState(() {
      _showHeart = true;
      _liked = true;
    });
    widget.onDoubleTap();
    Future.delayed(const Duration(milliseconds: 800), () {
      if (mounted) setState(() => _showHeart = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    final post = widget.post;
    final isDark = Theme.of(context).brightness == Brightness.dark;

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
                CircleAvatar(
                  radius: 16,
                  backgroundColor: Colors.grey[300],
                  child: Text(
                    (post['ai_name'] as String? ?? 'A')[0],
                    style: GoogleFonts.inter(
                      fontWeight: FontWeight.w600,
                      color: Colors.grey[700],
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Text(
                  post['ai_name'] ?? 'AI',
                  style: GoogleFonts.inter(
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
        ),

        // Image area with double-tap heart
        GestureDetector(
          onDoubleTap: _handleDoubleTap,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Post image placeholder (4:5 aspect ratio like Instagram)
              AspectRatio(
                aspectRatio: 4 / 5,
                child: Container(
                  width: double.infinity,
                  color: isDark
                      ? const Color(0xFF1A1A1A)
                      : const Color(0xFFF0F0F0),
                  child: post['media_url'] != null &&
                          (post['media_url'] as String).isNotEmpty
                      ? Image.network(
                          ApiClient.proxyImageUrl(post['media_url']),
                          fit: BoxFit.cover,
                          loadingBuilder: (context, child, progress) {
                            if (progress == null) return child;
                            return Center(
                              child: CircularProgressIndicator(
                                value: progress.expectedTotalBytes != null
                                    ? progress.cumulativeBytesLoaded /
                                        progress.expectedTotalBytes!
                                    : null,
                                strokeWidth: 2,
                                color: Colors.grey[400],
                              ),
                            );
                          },
                          errorBuilder: (context, error, stack) => Center(
                            child: Icon(Icons.broken_image_outlined,
                                size: 48, color: Colors.grey[400]),
                          ),
                        )
                      : Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.camera_alt_outlined,
                                size: 48,
                                color: Colors.grey[500],
                              ),
                              const SizedBox(height: 8),
                              Text(
                                post['caption'] ?? '',
                                textAlign: TextAlign.center,
                                style: GoogleFonts.inter(
                                  fontSize: 16,
                                  color: Colors.grey[500],
                                ),
                              ),
                            ],
                          ),
                        ),
                ),
              ),

              // Heart animation overlay
              if (_showHeart) const HeartAnimation(),
            ],
          ),
        ),

        // Action bar: like, comment, DM
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            children: [
              GestureDetector(
                onTap: () {
                  setState(() => _liked = !_liked);
                  if (_liked) widget.onDoubleTap();
                },
                child: Icon(
                  _liked ? Icons.favorite : Icons.favorite_border,
                  color: _liked ? const Color(0xFFED4956) : null,
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
            ],
          ),
        ),

        // Like count
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Text(
            '${post['like_count'] ?? 0} likes',
            style: GoogleFonts.inter(
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
          ),
        ),

        // Caption
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 4, 14, 12),
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

        Divider(height: 1, color: Colors.grey.withValues(alpha: 0.15)),
      ],
    );
  }
}
