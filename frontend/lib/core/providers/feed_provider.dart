import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/api_client.dart';

/// Feed posts provider with optimistic like support.
class FeedState {
  final List<Map<String, dynamic>> posts;
  final bool isLoading;
  final bool hasMore;
  final String? error;

  const FeedState({
    this.posts = const [],
    this.isLoading = false,
    this.hasMore = true,
    this.error,
  });

  FeedState copyWith({
    List<Map<String, dynamic>>? posts,
    bool? isLoading,
    bool? hasMore,
    String? error,
  }) {
    return FeedState(
      posts: posts ?? this.posts,
      isLoading: isLoading ?? this.isLoading,
      hasMore: hasMore ?? this.hasMore,
      error: error,
    );
  }
}

class FeedNotifier extends Notifier<FeedState> {
  @override
  FeedState build() {
    return const FeedState();
  }

  Future<void> loadPosts({bool refresh = false}) async {
    if (state.isLoading) return;
    state = state.copyWith(isLoading: true, error: null);

    try {
      final offset = refresh ? 0 : state.posts.length;
      final posts = await ApiClient.getList(
        '/api/feed/posts?limit=20&offset=$offset',
        useCache: refresh || offset == 0,
      );
      final typedPosts = posts.cast<Map<String, dynamic>>();

      if (refresh || offset == 0) {
        state = state.copyWith(
          posts: typedPosts,
          isLoading: false,
          hasMore: typedPosts.length >= 20,
        );
      } else {
        state = state.copyWith(
          posts: [...state.posts, ...typedPosts],
          isLoading: false,
          hasMore: typedPosts.length >= 20,
        );
      }
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  /// Optimistic like toggle — updates local state immediately.
  Future<void> toggleLike(int postId) async {
    final idx = state.posts.indexWhere((p) => p['id'] == postId);
    if (idx < 0) return;

    final post = Map<String, dynamic>.from(state.posts[idx]);
    final wasLiked = post['is_liked'] == true;
    final oldCount = (post['like_count'] as int?) ?? 0;

    // Optimistic update
    post['is_liked'] = !wasLiked;
    post['like_count'] = wasLiked ? oldCount - 1 : oldCount + 1;
    final updated = List<Map<String, dynamic>>.from(state.posts);
    updated[idx] = post;
    state = state.copyWith(posts: updated);

    try {
      if (wasLiked) {
        await ApiClient.delete('/api/feed/posts/$postId/like');
      } else {
        await ApiClient.post('/api/feed/posts/$postId/like', {});
      }
    } catch (_) {
      // Revert on failure
      post['is_liked'] = wasLiked;
      post['like_count'] = oldCount;
      final reverted = List<Map<String, dynamic>>.from(state.posts);
      reverted[idx] = post;
      state = state.copyWith(posts: reverted);
    }
  }

  /// Optimistic save toggle.
  Future<void> toggleSave(int postId) async {
    final idx = state.posts.indexWhere((p) => p['id'] == postId);
    if (idx < 0) return;

    final post = Map<String, dynamic>.from(state.posts[idx]);
    final wasSaved = post['is_saved'] == true;

    post['is_saved'] = !wasSaved;
    final updated = List<Map<String, dynamic>>.from(state.posts);
    updated[idx] = post;
    state = state.copyWith(posts: updated);

    try {
      if (wasSaved) {
        await ApiClient.delete('/api/feed/posts/$postId/save');
      } else {
        await ApiClient.post('/api/feed/posts/$postId/save', {});
      }
    } catch (_) {
      post['is_saved'] = wasSaved;
      final reverted = List<Map<String, dynamic>>.from(state.posts);
      reverted[idx] = post;
      state = state.copyWith(posts: reverted);
    }
  }
}

final feedProvider =
    NotifierProvider<FeedNotifier, FeedState>(FeedNotifier.new);

/// Stories provider
final storiesProvider = FutureProvider<List<dynamic>>((ref) async {
  return ApiClient.getList('/api/feed/stories');
});
