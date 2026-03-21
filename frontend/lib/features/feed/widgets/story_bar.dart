import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../core/api/api_client.dart';

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

    if (!_loading && groups.isEmpty) return const SizedBox.shrink();

    return Container(
      height: 110,
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: Theme.of(context).dividerColor.withValues(alpha: 0.2),
          ),
        ),
      ),
      child: _loading
          ? const Center(
              child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2)))
          : ListView.builder(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              itemCount: groups.length,
              itemBuilder: (context, index) {
                final group = groups[index];
                final name = group['ai_name'] as String;
                final aiId = group['ai_id'] as int;
                final stories = group['stories'] as List;
                final avatarUrl = group['ai_avatar'] as String;
                final hasUnviewed = group['has_unviewed'] == true;

                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 6),
                  child: GestureDetector(
                    onTap: () => widget.onStoryTap?.call(stories, aiId),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(3),
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            gradient: hasUnviewed
                                ? const LinearGradient(
                                    colors: [
                                      Color(0xFFF58529),
                                      Color(0xFFDD2A7B),
                                      Color(0xFF8134AF),
                                    ],
                                    begin: Alignment.topRight,
                                    end: Alignment.bottomLeft,
                                  )
                                : null,
                            border: hasUnviewed
                                ? null
                                : Border.all(
                                    color: Colors.grey[400]!, width: 1.5),
                          ),
                          child: Container(
                            padding: const EdgeInsets.all(2),
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: Theme.of(context).scaffoldBackgroundColor,
                            ),
                            child: avatarUrl.isNotEmpty
                                ? CircleAvatar(
                                    radius: 30,
                                    backgroundColor: Colors.grey[300],
                                    child: ClipOval(
                                      child: CachedNetworkImage(
                                        imageUrl: avatarUrl,
                                        width: 60,
                                        height: 60,
                                        fit: BoxFit.cover,
                                        errorWidget: (_, __, ___) => Text(
                                          name.isNotEmpty ? name[0] : 'A',
                                          style: GoogleFonts.inter(
                                            fontSize: 22,
                                            fontWeight: FontWeight.w600,
                                            color: Colors.grey[700],
                                          ),
                                        ),
                                      ),
                                    ),
                                  )
                                : CircleAvatar(
                                    radius: 30,
                                    backgroundColor: Colors.grey[300],
                                    child: Text(
                                      name.isNotEmpty ? name[0] : 'A',
                                      style: GoogleFonts.inter(
                                        fontSize: 22,
                                        fontWeight: FontWeight.w600,
                                        color: Colors.grey[700],
                                      ),
                                    ),
                                  ),
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          name,
                          style: GoogleFonts.inter(fontSize: 12),
                          overflow: TextOverflow.ellipsis,
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
