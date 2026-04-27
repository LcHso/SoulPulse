// ============================================================================
// SoulPulse Feed Page
// ============================================================================

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shimmer/shimmer.dart';
import '../../core/providers/feed_provider.dart';
import '../../core/providers/notification_provider.dart';
import '../../core/widgets/empty_state.dart';
import 'widgets/story_bar.dart';
import 'widgets/post_card_factory.dart';

/// Feed page component
///
/// Uses ConsumerStatefulWidget for Riverpod state management.
/// AutomaticKeepAliveClientMixin preserves page state across
/// bottom navigation tab switches.
class FeedPage extends ConsumerStatefulWidget {
  const FeedPage({super.key});

  @override
  ConsumerState<FeedPage> createState() => _FeedPageState();
}

class _FeedPageState extends ConsumerState<FeedPage>
    with AutomaticKeepAliveClientMixin {
  final _scrollCtrl = ScrollController();

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _scrollCtrl.addListener(_onScroll);
    Future.microtask(
        () => ref.read(feedProvider.notifier).loadPosts(refresh: true));
  }

  @override
  void dispose() {
    _scrollCtrl.removeListener(_onScroll);
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollCtrl.position.pixels >=
        _scrollCtrl.position.maxScrollExtent - 300) {
      final state = ref.read(feedProvider);
      if (!state.isLoading && state.hasMore) {
        ref.read(feedProvider.notifier).loadPosts();
      }
    }
  }

  void _openChat(Map<String, dynamic> post) {
    final aiId = post['ai_id'];
    final aiName = Uri.encodeComponent(post['ai_name'] ?? 'AI');
    final caption = post['caption'] as String?;

    var path = '/chat/$aiId?name=$aiName';

    if (caption != null && caption.isNotEmpty) {
      path += '&context=${Uri.encodeComponent(caption)}';
    }

    context.push(path);
  }

  void _openProfile(Map<String, dynamic> post) {
    final aiId = post['ai_id'];
    final aiName = Uri.encodeComponent(post['ai_name'] ?? 'AI');
    context.push('/ai/$aiId?name=${Uri.encodeComponent(aiName)}');
  }

  void _openStoryPlayer(List<dynamic> stories, int aiId) {
    if (stories.isEmpty) return;

    final aiName = stories.first['ai_name'] as String? ?? 'AI';

    context.push('/story', extra: {
      'stories': stories,
      'aiName': aiName,
      'aiId': aiId,
    });
  }

  void _openPostDetail(Map<String, dynamic> post) async {
    await context.push('/post-detail', extra: {
      'post': post,
      'aiName': post['ai_name'] ?? 'AI',
      'aiAvatar': post['ai_avatar'] ?? '',
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    final feedState = ref.watch(feedProvider);
    final notifState = ref.watch(notificationProvider);
    final notifUnread = notifState.unreadCount;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('SoulPulse'),
        actions: [
          IconButton(
            icon: Badge(
              isLabelVisible: notifUnread > 0,
              label: Text('$notifUnread'),
              child: const Icon(Icons.notifications_none),
            ),
            onPressed: () => context.push('/notifications'),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(feedProvider.notifier).loadPosts(refresh: true);
          ref.invalidate(storiesProvider);
        },
        child: feedState.isLoading && feedState.posts.isEmpty
            ? _buildShimmerLoading()
            : feedState.error != null && feedState.posts.isEmpty
                ? _buildErrorState(feedState.error!)
                : feedState.posts.isEmpty
                    ? _buildEmptyState()
                    : ListView.builder(
                        controller: _scrollCtrl,
                        itemCount: feedState.posts.length + 2,
                        itemBuilder: (context, index) {
                          if (index == 0) {
                            return StoryBar(onStoryTap: _openStoryPlayer);
                          }

                          if (index == feedState.posts.length + 1) {
                            if (feedState.isLoading) {
                              return const Padding(
                                padding: EdgeInsets.all(16),
                                child: Center(
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2)),
                              );
                            }

                            if (!feedState.hasMore) {
                              return Padding(
                                padding: const EdgeInsets.all(24),
                                child: Center(
                                  child: Text(
                                    'You\'re all caught up',
                                    style: Theme.of(context)
                                        .textTheme
                                        .bodySmall
                                        ?.copyWith(
                                          color: isDark
                                              ? const Color(0xFF9A9590)
                                              : const Color(0xFF8A8580),
                                        ),
                                  ),
                                ),
                              );
                            }

                            return const SizedBox.shrink();
                          }

                          // Post card with 12dp spacing
                          final post = feedState.posts[index - 1];
                          return Padding(
                            padding: const EdgeInsets.fromLTRB(8, 0, 8, 12),
                            child: PostCardFactory.build(
                              post: post,
                              onLike: () => ref
                                  .read(feedProvider.notifier)
                                  .toggleLike(post['id']),
                              onSave: () => ref
                                  .read(feedProvider.notifier)
                                  .toggleSave(post['id']),
                              onDM: () => _openChat(post),
                              onProfileTap: () => _openProfile(post),
                              onComment: () => _openPostDetail(post),
                            ),
                          );
                        },
                      ),
      ),
    );
  }

  // ================== Skeleton loading ==================

  Widget _buildShimmerLoading() {
    return ListView.builder(
      itemCount: 4,
      itemBuilder: (context, index) {
        if (index == 0) {
          return _buildStoryBarShimmer();
        }
        return _buildPostShimmer();
      },
    );
  }

  Widget _buildStoryBarShimmer() {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    // Warm gray tones matching the theme
    final baseColor =
        isDark ? const Color(0xFF2A2A42) : const Color(0xFFE8E4DF);
    final highlightColor =
        isDark ? const Color(0xFF3A3A55) : const Color(0xFFF5F2EE);

    return Shimmer.fromColors(
      baseColor: baseColor,
      highlightColor: highlightColor,
      child: Container(
        height: 118,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: List.generate(
              5,
              (_) => Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const CircleAvatar(radius: 32),
                        const SizedBox(height: 6),
                        Container(width: 44, height: 10, color: Colors.white),
                      ],
                    ),
                  )),
        ),
      ),
    );
  }

  Widget _buildPostShimmer() {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    // Warm gray tones matching the theme
    final baseColor =
        isDark ? const Color(0xFF2A2A42) : const Color(0xFFE8E4DF);
    final highlightColor =
        isDark ? const Color(0xFF3A3A55) : const Color(0xFFF5F2EE);

    return Shimmer.fromColors(
      baseColor: baseColor,
      highlightColor: highlightColor,
      child: Container(
        margin: const EdgeInsets.fromLTRB(8, 0, 8, 12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          color: Colors.white,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header area
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
              child: Row(
                children: [
                  const CircleAvatar(radius: 16),
                  const SizedBox(width: 10),
                  Container(width: 80, height: 12, color: Colors.white),
                ],
              ),
            ),

            // Image area
            AspectRatio(
              aspectRatio: 4 / 5,
              child: Container(color: Colors.white),
            ),

            // Bottom area
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(width: 60, height: 12, color: Colors.white),
                  const SizedBox(height: 8),
                  Container(
                      width: double.infinity, height: 10, color: Colors.white),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ================== State pages ==================

  Widget _buildErrorState(String error) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final warmGray = isDark ? const Color(0xFF9A9590) : const Color(0xFF8A8580);

    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.error_outline, size: 48, color: warmGray),
          const SizedBox(height: 16),
          Text('Failed to load feed',
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: warmGray)),
          const SizedBox(height: 8),
          TextButton(
            onPressed: () =>
                ref.read(feedProvider.notifier).loadPosts(refresh: true),
            child: const Text('Retry'),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return ListView(
      children: [
        StoryBar(onStoryTap: _openStoryPlayer),
        const SizedBox(height: 80),
        const EmptyState(
          icon: Icons.photo_library_outlined,
          title: 'Your feed is empty',
          subtitle: 'Follow AI companions to see their posts',
        ),
      ],
    );
  }
}
