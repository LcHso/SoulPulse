import 'package:flutter/material.dart';
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
      // Silently fail — story bar is non-critical
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Group stories by ai_id, keeping the latest story per persona.
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
        };
      }
      (grouped[aiId]!['stories'] as List).add(story);
    }
    return grouped.values.toList();
  }

  @override
  Widget build(BuildContext context) {
    final groups = _groupByPersona();

    // Show nothing if no stories and done loading
    if (!_loading && groups.isEmpty) {
      return const SizedBox.shrink();
    }

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
          ? const Center(child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)))
          : ListView.builder(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              itemCount: groups.length,
              itemBuilder: (context, index) {
                final group = groups[index];
                final name = group['ai_name'] as String;
                final aiId = group['ai_id'] as int;
                final stories = group['stories'] as List;

                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 6),
                  child: GestureDetector(
                    onTap: () => widget.onStoryTap?.call(stories, aiId),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // Gradient ring around avatar
                        Container(
                          padding: const EdgeInsets.all(3),
                          decoration: const BoxDecoration(
                            shape: BoxShape.circle,
                            gradient: LinearGradient(
                              colors: [
                                Color(0xFFF58529),
                                Color(0xFFDD2A7B),
                                Color(0xFF8134AF),
                              ],
                              begin: Alignment.topRight,
                              end: Alignment.bottomLeft,
                            ),
                          ),
                          child: Container(
                            padding: const EdgeInsets.all(2),
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: Theme.of(context).scaffoldBackgroundColor,
                            ),
                            child: CircleAvatar(
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
