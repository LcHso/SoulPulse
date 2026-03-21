import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shimmer/shimmer.dart';
import '../../core/providers/feed_provider.dart';
import '../../core/providers/notification_provider.dart';
import 'widgets/story_bar.dart';
import 'widgets/post_card.dart';

class FeedPage extends ConsumerStatefulWidget {
  const FeedPage({super.key});

  @override
  ConsumerState<FeedPage> createState() => _FeedPageState();
}

class _FeedPageState extends ConsumerState<FeedPage> {
  final _scrollCtrl = ScrollController();

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
    context.push('/ai/$aiId?name=$aiName');
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
    final feedState = ref.watch(feedProvider);
    final notifState = ref.watch(notificationProvider);
    final notifUnread = notifState.unreadCount;

    return Scaffold(
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
                        itemCount: feedState.posts.length +
                            2, // +1 story bar, +1 loading
                        itemBuilder: (context, index) {
                          if (index == 0) {
                            return StoryBar(onStoryTap: _openStoryPlayer);
                          }
                          if (index == feedState.posts.length + 1) {
                            // Bottom loading indicator
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
                                    style: TextStyle(
                                        color: Colors.grey[500], fontSize: 13),
                                  ),
                                ),
                              );
                            }
                            return const SizedBox.shrink();
                          }
                          final post = feedState.posts[index - 1];
                          return PostCard(
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
                          );
                        },
                      ),
      ),
    );
  }

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
    return Shimmer.fromColors(
      baseColor: isDark ? Colors.grey[800]! : Colors.grey[300]!,
      highlightColor: isDark ? Colors.grey[700]! : Colors.grey[100]!,
      child: Container(
        height: 110,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: List.generate(
              5,
              (_) => Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 6),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const CircleAvatar(radius: 30),
                        const SizedBox(height: 4),
                        Container(width: 40, height: 10, color: Colors.white),
                      ],
                    ),
                  )),
        ),
      ),
    );
  }

  Widget _buildPostShimmer() {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Shimmer.fromColors(
      baseColor: isDark ? Colors.grey[800]! : Colors.grey[300]!,
      highlightColor: isDark ? Colors.grey[700]! : Colors.grey[100]!,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Row(
              children: [
                const CircleAvatar(radius: 16),
                const SizedBox(width: 10),
                Container(width: 80, height: 12, color: Colors.white),
              ],
            ),
          ),
          AspectRatio(
            aspectRatio: 4 / 5,
            child: Container(color: Colors.white),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
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
    );
  }

  Widget _buildErrorState(String error) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.error_outline, size: 48, color: Colors.grey[400]),
          const SizedBox(height: 16),
          Text('Failed to load feed',
              style: TextStyle(color: Colors.grey[500])),
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
        Center(
          child: Column(
            children: [
              Icon(Icons.photo_library_outlined,
                  size: 64, color: Colors.grey[300]),
              const SizedBox(height: 16),
              Text('No posts yet',
                  style: TextStyle(fontSize: 16, color: Colors.grey[500])),
              const SizedBox(height: 8),
              Text('Discover AI personas and start connecting!',
                  style: TextStyle(fontSize: 13, color: Colors.grey[400])),
            ],
          ),
        ),
      ],
    );
  }
}
