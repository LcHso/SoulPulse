import 'package:flutter/material.dart';
import '../../core/api/api_client.dart';
import 'widgets/story_bar.dart';
import 'widgets/post_card.dart';
import 'story_player_page.dart';
import '../chat/chat_page.dart';
import '../auth/login_page.dart';
import '../profile/ai_profile_page.dart';
import '../profile/post_detail_page.dart';

class FeedPage extends StatefulWidget {
  const FeedPage({super.key});

  @override
  State<FeedPage> createState() => _FeedPageState();
}

class _FeedPageState extends State<FeedPage> {
  List<dynamic> _posts = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadPosts();
  }

  Future<void> _loadPosts() async {
    setState(() => _loading = true);
    try {
      final posts = await ApiClient.getList('/api/feed/posts');
      setState(() => _posts = posts);
    } catch (e) {
      // Show error in a snackbar
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to load feed: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _likePost(int postId) async {
    try {
      await ApiClient.post('/api/feed/posts/$postId/like', {});
      _loadPosts();
    } catch (_) {}
  }

  void _openChat(Map<String, dynamic> post) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ChatPage(
          aiId: post['ai_id'],
          aiName: post['ai_name'],
          postContext: post['caption'],
        ),
      ),
    );
  }

  void _openProfile(Map<String, dynamic> post) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => AIProfilePage(
          aiId: post['ai_id'],
          aiName: post['ai_name'] ?? 'AI',
        ),
      ),
    );
  }

  void _openStoryPlayer(List<dynamic> stories, int aiId) {
    if (stories.isEmpty) return;
    final aiName = stories.first['ai_name'] as String? ?? 'AI';
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => StoryPlayerPage(
          stories: stories,
          aiName: aiName,
          aiId: aiId,
        ),
      ),
    );
  }

  void _openPostDetail(Map<String, dynamic> post) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => PostDetailPage(
          post: post,
          aiName: post['ai_name'] ?? 'AI',
          aiAvatar: post['ai_avatar'] ?? '',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('SoulPulse'),
        actions: [
          IconButton(
            icon: const Icon(Icons.chat_bubble_outline),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => const ChatPage(
                    aiId: 1,
                    aiName: 'Ethan',
                  ),
                ),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await ApiClient.clearToken();
              if (!context.mounted) return;
              Navigator.of(context).pushReplacement(
                MaterialPageRoute(builder: (_) => const LoginPage()),
              );
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadPosts,
        child: _loading && _posts.isEmpty
            ? const Center(child: CircularProgressIndicator())
            : ListView.builder(
                itemCount: _posts.length + 1, // +1 for story bar
                itemBuilder: (context, index) {
                  if (index == 0) {
                    return StoryBar(onStoryTap: _openStoryPlayer);
                  }
                  final post = _posts[index - 1];
                  return PostCard(
                    post: post,
                    onDoubleTap: () => _likePost(post['id']),
                    onDM: () => _openChat(post),
                    onProfileTap: () => _openProfile(post),
                    onComment: () => _openPostDetail(post),
                  );
                },
              ),
      ),
    );
  }
}
