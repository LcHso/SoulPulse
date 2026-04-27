import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:timeago/timeago.dart' as timeago;
import '../../../core/api/api_client.dart';
import '../../../core/theme/character_theme.dart';

/// Pure text post card component
///
/// Displays text-only posts with large Playfair Display typography
/// and a character gradient background with glass-morphism-lite effect,
/// creating a premium quote-card visual style.
class PostCardText extends StatefulWidget {
  final Map<String, dynamic> post;
  final VoidCallback onLike;
  final VoidCallback? onSave;
  final VoidCallback onDM;
  final VoidCallback? onProfileTap;
  final VoidCallback? onComment;

  const PostCardText({
    super.key,
    required this.post,
    required this.onLike,
    this.onSave,
    required this.onDM,
    this.onProfileTap,
    this.onComment,
  });

  @override
  State<PostCardText> createState() => _PostCardTextState();
}

class _PostCardTextState extends State<PostCardText> {
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
    final avatarUrl =
        ApiClient.proxyImageUrl(post['ai_avatar'] as String? ?? '');
    final createdAt = post['created_at'] as String?;
    final aiName = post['ai_name'] as String? ?? 'AI';
    final caption = post['caption'] as String? ?? '';

    // Get character-specific colors
    final characterColors = CharacterTheme.getPalette(aiName);

    // Warm card styling
    final cardColor = isDark ? const Color(0xFF22223A) : Colors.white;
    final warmShadow = isDark
        ? Colors.black.withValues(alpha: 0.3)
        : const Color(0xFF2D2926).withValues(alpha: 0.06);
    final warmGray = isDark ? const Color(0xFF9A9590) : const Color(0xFF8A8580);
    final quoteTextColor =
        isDark ? const Color(0xFFF0ECE8) : const Color(0xFF2D2926);

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: cardColor,
        boxShadow: [
          BoxShadow(
            color: warmShadow,
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Stack(
          children: [
            // Main content
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header: avatar + name (consistent with image cards)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                  child: GestureDetector(
                    onTap: widget.onProfileTap,
                    child: Row(
                      children: [
                        _buildAvatar(
                          avatarUrl,
                          aiName,
                          16,
                          borderColor: characterColors.primary,
                        ),
                        const SizedBox(width: 10),
                        Text(
                          aiName,
                          style: GoogleFonts.inter(
                            fontWeight: FontWeight.w600,
                            fontSize: 14,
                            color: characterColors.primary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

                // Text content area with gradient background and glass effect
                Container(
                  width: double.infinity,
                  margin: const EdgeInsets.symmetric(horizontal: 12),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        characterColors.primary.withValues(alpha: 0.08),
                        characterColors.vibrant.withValues(alpha: 0.12),
                        characterColors.primary.withValues(alpha: 0.06),
                      ],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: characterColors.primary.withValues(alpha: 0.08),
                      width: 1,
                    ),
                  ),
                  child: Stack(
                    children: [
                      // Decorative quote mark at top-left
                      Positioned(
                        top: -16,
                        left: -4,
                        child: Text(
                          '\u201C',
                          style: TextStyle(
                            fontSize: 72,
                            fontWeight: FontWeight.w700,
                            color:
                                characterColors.primary.withValues(alpha: 0.15),
                            height: 1.0,
                          ),
                        ),
                      ),

                      // Main text content in Playfair Display
                      Padding(
                        padding: const EdgeInsets.only(
                            top: 16), // offset for the decorative quote mark
                        child: Text(
                          caption,
                          style: GoogleFonts.playfairDisplay(
                            fontSize: 20,
                            fontWeight: FontWeight.w500,
                            height: 1.6,
                            color: quoteTextColor,
                            letterSpacing: -0.2,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),

                // Action bar: like, comment, DM, save — with larger touch targets
                Padding(
                  padding: const EdgeInsets.fromLTRB(4, 8, 4, 4),
                  child: Row(
                    children: [
                      _buildActionButton(
                        icon: isLiked ? Icons.favorite : Icons.favorite_border,
                        color: isLiked ? characterColors.primary : null,
                        size: 26,
                        onTap: () {
                          widget.onLike();
                          HapticFeedback.lightImpact();
                        },
                      ),
                      _buildActionButton(
                        icon: Icons.chat_bubble_outline,
                        size: 24,
                        onTap: widget.onComment,
                      ),
                      _buildActionButton(
                        icon: Icons.send_outlined,
                        size: 24,
                        onTap: widget.onDM,
                      ),
                      const Spacer(),
                      if (widget.onSave != null)
                        _buildActionButton(
                          icon:
                              isSaved ? Icons.bookmark : Icons.bookmark_border,
                          color: isSaved
                              ? Theme.of(context).colorScheme.primary
                              : null,
                          size: 26,
                          onTap: () {
                            widget.onSave!();
                            HapticFeedback.lightImpact();
                          },
                        ),
                    ],
                  ),
                ),

                // Like count
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                    '$likeCount likes',
                    style: GoogleFonts.inter(
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                      color: isDark
                          ? const Color(0xFFF0ECE8)
                          : const Color(0xFF2D2926),
                    ),
                  ),
                ),

                // Comment count
                if (commentCount > 0)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
                    child: GestureDetector(
                      onTap: widget.onComment,
                      child: Text(
                        'View all $commentCount comments',
                        style: GoogleFonts.inter(fontSize: 13, color: warmGray),
                      ),
                    ),
                  ),

                // Timestamp
                if (createdAt != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
                    child: Text(
                      _formatTime(createdAt),
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: warmGray,
                          ),
                    ),
                  ),
              ],
            ),

            // Left gradient stripe (4dp wide, full card height)
            Positioned(
              left: 0,
              top: 0,
              bottom: 0,
              child: Container(
                width: 4,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      characterColors.primary,
                      characterColors.vibrant,
                      characterColors.primary,
                    ],
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Builds a touch-friendly action button with 44dp minimum tap target
  Widget _buildActionButton({
    required IconData icon,
    required VoidCallback? onTap,
    Color? color,
    double size = 24,
  }) {
    return SizedBox(
      width: 44,
      height: 44,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Center(
          child: Icon(icon, color: color, size: size),
        ),
      ),
    );
  }

  Widget _buildAvatar(String url, String name, double radius,
      {Color? borderColor}) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final placeholderBg =
        isDark ? const Color(0xFF333350) : const Color(0xFFF0ECE8);
    final placeholderText =
        isDark ? const Color(0xFFF0ECE8) : const Color(0xFF2D2926);

    final avatar = url.isNotEmpty
        ? CircleAvatar(
            radius: radius - 2,
            backgroundColor: placeholderBg,
            child: ClipOval(
              child: CachedNetworkImage(
                imageUrl: url,
                width: (radius - 2) * 2,
                height: (radius - 2) * 2,
                fit: BoxFit.cover,
                errorWidget: (_, __, ___) => Text(
                  name.isNotEmpty ? name[0] : 'A',
                  style: GoogleFonts.inter(
                      fontWeight: FontWeight.w600, color: placeholderText),
                ),
              ),
            ),
          )
        : CircleAvatar(
            radius: radius - 2,
            backgroundColor: placeholderBg,
            child: Text(
              name.isNotEmpty ? name[0] : 'A',
              style: GoogleFonts.inter(
                  fontWeight: FontWeight.w600, color: placeholderText),
            ),
          );

    // Wrap with colored border ring if borderColor is provided
    if (borderColor != null) {
      return Container(
        padding: const EdgeInsets.all(2),
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: borderColor, width: 2),
        ),
        child: avatar,
      );
    }
    return avatar;
  }
}
