import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../core/api/api_client.dart';
import '../../../core/theme/character_theme.dart';

class StoryBar extends StatefulWidget {
  final void Function(List<dynamic> stories, int aiId)? onStoryTap;

  const StoryBar({super.key, this.onStoryTap});

  @override
  State<StoryBar> createState() => _StoryBarState();
}

class _StoryBarState extends State<StoryBar> {
  List<dynamic> _stories = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadStories();
  }

  Future<void> _loadStories() async {
    try {
      final stories = await ApiClient.getList('/api/feed/stories');
      if (mounted) setState(() => _stories = stories);
    } catch (_) {
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<Map<String, dynamic>> _groupByPersona() {
    final Map<int, Map<String, dynamic>> grouped = {};
    for (final story in _stories) {
      final aiId = story['ai_id'] as int;
      if (!grouped.containsKey(aiId)) {
        grouped[aiId] = {
          'ai_id': aiId,
          'ai_name': story['ai_name'] as String,
          'ai_avatar': story['ai_avatar'] as String? ?? '',
          'stories': <dynamic>[],
          'has_unviewed': false,
        };
      }
      (grouped[aiId]!['stories'] as List).add(story);
      if (story['is_viewed'] != true) {
        grouped[aiId]!['has_unviewed'] = true;
      }
    }
    return grouped.values.toList();
  }

  @override
  Widget build(BuildContext context) {
    final groups = _groupByPersona();
    final isDark = Theme.of(context).brightness == Brightness.dark;

    if (!_loading && groups.isEmpty) return const SizedBox.shrink();

    // Warm text colors
    final nameTextColor =
        isDark ? const Color(0xFFF0ECE8) : const Color(0xFF2D2926);
    final scaffoldBg = Theme.of(context).scaffoldBackgroundColor;

    return Container(
      height: 118,
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: _loading
          ? Center(
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
            )
          : ListView.builder(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              itemCount: groups.length,
              itemBuilder: (context, index) {
                final group = groups[index];
                final name = group['ai_name'] as String;
                final aiId = group['ai_id'] as int;
                final stories = group['stories'] as List;
                final avatarUrl =
                    ApiClient.proxyImageUrl(group['ai_avatar'] as String);
                final hasUnviewed = group['has_unviewed'] == true;

                final characterColors = CharacterTheme.getPalette(name);

                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  child: GestureDetector(
                    onTap: () => widget.onStoryTap?.call(stories, aiId),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // Avatar with gradient ring and outer glow
                        Container(
                          padding: const EdgeInsets.all(3),
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            gradient: hasUnviewed
                                ? CharacterTheme.createStoryGradient(
                                    characterColors,
                                    brightness: isDark
                                        ? Brightness.dark
                                        : Brightness.light,
                                  )
                                : null,
                            border: hasUnviewed
                                ? null
                                : Border.all(
                                    color: isDark
                                        ? const Color(0xFF555566)
                                        : Colors.grey[400]!,
                                    width: 1.5),
                            boxShadow: hasUnviewed
                                ? [
                                    BoxShadow(
                                      color: characterColors.vibrant
                                          .withValues(alpha: 0.3),
                                      blurRadius: 6,
                                      spreadRadius: 1,
                                    ),
                                  ]
                                : null,
                          ),
                          child: Container(
                            padding: const EdgeInsets.all(2),
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: scaffoldBg,
                            ),
                            child: avatarUrl.isNotEmpty
                                ? CircleAvatar(
                                    radius: 32,
                                    backgroundColor: isDark
                                        ? const Color(0xFF333350)
                                        : const Color(0xFFF0ECE8),
                                    child: ClipOval(
                                      child: CachedNetworkImage(
                                        imageUrl: avatarUrl,
                                        width: 64,
                                        height: 64,
                                        fit: BoxFit.cover,
                                        errorWidget: (_, __, ___) => Text(
                                          name.isNotEmpty ? name[0] : 'A',
                                          style: GoogleFonts.inter(
                                            fontSize: 24,
                                            fontWeight: FontWeight.w600,
                                            color: isDark
                                                ? const Color(0xFFF0ECE8)
                                                : const Color(0xFF2D2926),
                                          ),
                                        ),
                                      ),
                                    ),
                                  )
                                : CircleAvatar(
                                    radius: 32,
                                    backgroundColor: isDark
                                        ? const Color(0xFF333350)
                                        : const Color(0xFFF0ECE8),
                                    child: Text(
                                      name.isNotEmpty ? name[0] : 'A',
                                      style: GoogleFonts.inter(
                                        fontSize: 24,
                                        fontWeight: FontWeight.w600,
                                        color: isDark
                                            ? const Color(0xFFF0ECE8)
                                            : const Color(0xFF2D2926),
                                      ),
                                    ),
                                  ),
                          ),
                        ),
                        const SizedBox(height: 6),
                        // Name text: Inter medium 12sp, warm text color
                        SizedBox(
                          width: 72,
                          child: Text(
                            name,
                            style: GoogleFonts.inter(
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: nameTextColor,
                            ),
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.center,
                            maxLines: 1,
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}
