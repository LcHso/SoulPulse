import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../../core/providers/auth_provider.dart';
import '../../core/api/api_client.dart';

final _interactionsProvider = FutureProvider<List<dynamic>>((ref) async {
  return ApiClient.getList('/api/ai/interactions/summary');
});

class UserProfilePage extends ConsumerWidget {
  const UserProfilePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
    final interactionsAsync = ref.watch(_interactionsProvider);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final user = authState.user;

    return Scaffold(
      appBar: AppBar(
        title: Text('Profile',
            style:
                GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 22)),
        actions: [
          IconButton(
            icon: const Icon(Icons.notifications_outlined),
            onPressed: () => context.push('/notifications'),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => context.push('/settings'),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(authProvider.notifier).loadUser();
          ref.invalidate(_interactionsProvider);
        },
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // User info card
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF1C1C1E) : Colors.white,
                borderRadius: BorderRadius.circular(16),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withAlpha(isDark ? 40 : 15),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 36,
                    backgroundColor: const Color(0xFF0095F6),
                    child: Text(
                      (user?['nickname'] as String? ?? 'U')[0].toUpperCase(),
                      style: GoogleFonts.inter(
                          fontSize: 28,
                          fontWeight: FontWeight.w700,
                          color: Colors.white),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          user?['nickname'] ?? 'User',
                          style: GoogleFonts.inter(
                              fontWeight: FontWeight.w700, fontSize: 18),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          user?['email'] ?? '',
                          style: GoogleFonts.inter(
                              fontSize: 13, color: Colors.grey[500]),
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Icon(Icons.diamond_outlined,
                                size: 16, color: Colors.amber[600]),
                            const SizedBox(width: 4),
                            Text(
                              '${user?['gem_balance'] ?? 0} Gems',
                              style: GoogleFonts.inter(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: Colors.amber[700]),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // Relationships section
            Text(
              'My Relationships',
              style:
                  GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 16),
            ),
            const SizedBox(height: 12),

            interactionsAsync.when(
              loading: () => const Center(
                  child: Padding(
                padding: EdgeInsets.all(20),
                child: CircularProgressIndicator(strokeWidth: 2),
              )),
              error: (_, __) => Center(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Text('Failed to load relationships',
                      style: GoogleFonts.inter(color: Colors.grey)),
                ),
              ),
              data: (interactions) {
                if (interactions.isEmpty) {
                  return Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: isDark ? const Color(0xFF1C1C1E) : Colors.grey[50],
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      children: [
                        Icon(Icons.people_outline,
                            size: 48, color: Colors.grey[400]),
                        const SizedBox(height: 12),
                        Text('No relationships yet',
                            style: GoogleFonts.inter(color: Colors.grey)),
                        const SizedBox(height: 8),
                        TextButton(
                          onPressed: () => context.go('/discover'),
                          child: const Text('Find AI Companions'),
                        ),
                      ],
                    ),
                  );
                }
                return Column(
                  children: interactions.map<Widget>((i) {
                    final item = i as Map<String, dynamic>;
                    final intimacy =
                        (item['intimacy_score'] as num?)?.toDouble() ?? 0;
                    final hint =
                        item['emotion_hint'] as Map<String, dynamic>? ?? {};
                    return _RelationshipCard(
                      item: item,
                      intimacy: intimacy,
                      emotionHint: hint,
                      isDark: isDark,
                      onTap: () {
                        final aiId = item['ai_id'] as int;
                        final name = item['ai_name'] as String? ?? 'AI';
                        context.push(
                            '/ai/$aiId?name=${Uri.encodeComponent(name)}');
                      },
                    );
                  }).toList(),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _RelationshipCard extends StatelessWidget {
  final Map<String, dynamic> item;
  final double intimacy;
  final Map<String, dynamic> emotionHint;
  final bool isDark;
  final VoidCallback onTap;

  const _RelationshipCard({
    required this.item,
    required this.intimacy,
    required this.emotionHint,
    required this.isDark,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final name = item['ai_name'] as String? ?? 'AI';
    final avatar = item['ai_avatar'] as String? ?? '';
    final level = item['intimacy_level'] as String? ?? 'Stranger';
    final mood = emotionHint['mood'] as String? ?? 'neutral';

    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF1C1C1E) : Colors.white,
          borderRadius: BorderRadius.circular(12),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withAlpha(isDark ? 30 : 10),
              blurRadius: 4,
            ),
          ],
        ),
        child: Row(
          children: [
            CircleAvatar(
              radius: 24,
              backgroundColor: Colors.grey[300],
              backgroundImage:
                  avatar.isNotEmpty ? CachedNetworkImageProvider(avatar) : null,
              child: avatar.isEmpty
                  ? Text(name[0],
                      style: GoogleFonts.inter(
                          fontWeight: FontWeight.w600, color: Colors.grey[700]))
                  : null,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(name,
                          style: GoogleFonts.inter(
                              fontWeight: FontWeight.w600, fontSize: 14)),
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: _levelColor(level).withAlpha(30),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(level,
                            style: GoogleFonts.inter(
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                                color: _levelColor(level))),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  // Intimacy progress bar
                  Row(
                    children: [
                      Expanded(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(4),
                          child: LinearProgressIndicator(
                            value: intimacy / 10.0,
                            backgroundColor:
                                isDark ? Colors.grey[800] : Colors.grey[200],
                            valueColor:
                                AlwaysStoppedAnimation(_levelColor(level)),
                            minHeight: 6,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text('${intimacy.toStringAsFixed(1)}/10',
                          style: GoogleFonts.inter(
                              fontSize: 11, color: Colors.grey[500])),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            // Mood indicator
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: _moodColor(mood).withAlpha(25),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(mood,
                  style: GoogleFonts.inter(
                      fontSize: 11,
                      color: _moodColor(mood),
                      fontWeight: FontWeight.w500)),
            ),
          ],
        ),
      ),
    );
  }

  Color _levelColor(String level) {
    switch (level) {
      case 'Soulmate':
        return Colors.pink;
      case 'Close Friend':
        return Colors.purple;
      case 'Friend':
        return const Color(0xFF0095F6);
      case 'Acquaintance':
        return Colors.green;
      default:
        return Colors.grey;
    }
  }

  Color _moodColor(String mood) {
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
        return Colors.grey;
    }
  }
}
