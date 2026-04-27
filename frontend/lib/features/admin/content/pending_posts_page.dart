import 'package:flutter/material.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../../../core/api/api_client.dart';

/// Pending posts review page with waterfall grid layout.
class PendingPostsPage extends ConsumerStatefulWidget {
  const PendingPostsPage({super.key});

  @override
  ConsumerState<PendingPostsPage> createState() => _PendingPostsPageState();
}

class _PendingPostsPageState extends ConsumerState<PendingPostsPage> {
  List<Map<String, dynamic>> _posts = [];
  bool _isLoading = true;
  bool _hasMore = true;
  int _offset = 0;
  final int _limit = 20;
  int _statusFilter = 0; // 0=pending, 1=published, -1=all

  @override
  void initState() {
    super.initState();
    _loadPosts();
  }

  Future<void> _loadPosts({bool refresh = false}) async {
    if (refresh) {
      setState(() {
        _posts = [];
        _offset = 0;
        _hasMore = true;
      });
    }

    if (!_hasMore) return;

    setState(() => _isLoading = true);

    try {
      String path;
      if (_statusFilter == -1) {
        path = '/api/admin/posts/all?limit=$_limit&offset=$_offset';
      } else if (_statusFilter == 0) {
        path = '/api/admin/posts/pending?limit=$_limit&offset=$_offset';
      } else {
        path =
            '/api/admin/posts/all?limit=$_limit&offset=$_offset&status=$_statusFilter';
      }
      final response = await ApiClient.get(path, useCache: false);

      final posts = List<Map<String, dynamic>>.from(response['posts'] ?? []);
      final total = response['total'] ?? 0;

      setState(() {
        _posts.addAll(posts);
        _offset += posts.length;
        _hasMore = _offset < total;
        _isLoading = false;
      });
    } catch (e) {
      setState(() => _isLoading = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error loading posts: $e')),
        );
      }
    }
  }

  Future<void> _approvePost(int postId) async {
    try {
      await ApiClient.post('/api/admin/posts/$postId/approve', {});
      setState(() {
        _posts.removeWhere((p) => p['id'] == postId);
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Post approved!')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error approving: $e')),
        );
      }
    }
  }

  Future<void> _rejectPost(int postId) async {
    try {
      await ApiClient.post('/api/admin/posts/$postId/reject', {});
      setState(() {
        _posts.removeWhere((p) => p['id'] == postId);
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Post rejected')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error rejecting: $e')),
        );
      }
    }
  }

  Future<void> _regeneratePost(int postId) async {
    try {
      final response =
          await ApiClient.post('/api/admin/posts/$postId/regenerate', {});
      // Update the post with new media_url
      final index = _posts.indexWhere((p) => p['id'] == postId);
      if (index != -1) {
        setState(() {
          _posts[index]['media_url'] = response['media_url'];
        });
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Image regenerated!')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error regenerating: $e')),
        );
      }
    }
  }

  Future<void> _deletePost(int postId) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Post'),
        content: const Text('Are you sure? This cannot be undone.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      await ApiClient.delete('/api/admin/posts/$postId');
      setState(() {
        _posts.removeWhere((p) => p['id'] == postId);
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Post deleted')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error deleting: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Posts (${_posts.length})'),
        backgroundColor: Colors.deepPurple,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => _loadPosts(refresh: true),
          ),
        ],
      ),
      body: Column(
        children: [
          // Filter chips
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                for (final entry in {
                  -1: 'All',
                  0: 'Pending',
                  1: 'Published',
                  2: 'Rejected'
                }.entries)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(entry.value),
                      selected: _statusFilter == entry.key,
                      onSelected: (_) {
                        setState(() => _statusFilter = entry.key);
                        _loadPosts(refresh: true);
                      },
                    ),
                  ),
              ],
            ),
          ),
          Expanded(
            child: _isLoading && _posts.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : _posts.isEmpty
                    ? const Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.check_circle_outline,
                                size: 64, color: Colors.grey),
                            SizedBox(height: 16),
                            Text('No posts found',
                                style: TextStyle(
                                    fontSize: 18, color: Colors.grey)),
                          ],
                        ),
                      )
                    : MasonryGridView.count(
                        crossAxisCount: 3,
                        mainAxisSpacing: 16,
                        crossAxisSpacing: 16,
                        padding: const EdgeInsets.all(16),
                        itemCount: _posts.length + (_hasMore ? 1 : 0),
                        itemBuilder: (context, index) {
                          if (index == _posts.length) {
                            // Load more button
                            return Center(
                              child: ElevatedButton(
                                onPressed: _isLoading ? null : _loadPosts,
                                child: _isLoading
                                    ? const SizedBox(
                                        width: 20,
                                        height: 20,
                                        child: CircularProgressIndicator(
                                            strokeWidth: 2),
                                      )
                                    : const Text('Load More'),
                              ),
                            );
                          }

                          final post = _posts[index];
                          return _PostCard(
                            post: post,
                            onApprove: () => _approvePost(post['id']),
                            onReject: () => _rejectPost(post['id']),
                            onRegenerate: () => _regeneratePost(post['id']),
                            onDelete: () => _deletePost(post['id']),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}

class _PostCard extends StatelessWidget {
  final Map<String, dynamic> post;
  final VoidCallback onApprove;
  final VoidCallback onReject;
  final VoidCallback onRegenerate;
  final VoidCallback onDelete;

  const _PostCard({
    required this.post,
    required this.onApprove,
    required this.onReject,
    required this.onRegenerate,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final mediaUrl =
        ApiClient.proxyImageUrl(post['media_url'] as String? ?? '');
    final caption = post['caption'] ?? '';
    final aiName = post['ai_name'] ?? 'Unknown';
    final aiAvatar =
        ApiClient.proxyImageUrl(post['ai_avatar'] as String? ?? '');
    final createdAt = post['created_at'] ?? '';

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // AI info header
          Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 16,
                  backgroundImage: aiAvatar.isNotEmpty
                      ? CachedNetworkImageProvider(aiAvatar)
                      : null,
                  child:
                      aiAvatar.isEmpty ? Text(aiName[0].toUpperCase()) : null,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        aiName,
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      Text(
                        _formatDate(createdAt),
                        style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          // Image
          if (mediaUrl.isNotEmpty)
            CachedNetworkImage(
              imageUrl: mediaUrl,
              fit: BoxFit.cover,
              placeholder: (context, url) => const AspectRatio(
                aspectRatio: 4 / 5,
                child: Center(child: CircularProgressIndicator()),
              ),
              errorWidget: (context, url, error) => Container(
                height: 200,
                color: Colors.grey[200],
                child: const Center(child: Icon(Icons.broken_image)),
              ),
            ),
          // Caption
          Padding(
            padding: const EdgeInsets.all(8),
            child: Text(
              caption,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 13),
            ),
          ),
          // Action buttons
          OverflowBar(
            alignment: MainAxisAlignment.spaceEvenly,
            children: [
              IconButton(
                icon: const Icon(Icons.check, color: Colors.green),
                tooltip: 'Approve',
                onPressed: onApprove,
              ),
              IconButton(
                icon: const Icon(Icons.close, color: Colors.red),
                tooltip: 'Reject',
                onPressed: onReject,
              ),
              IconButton(
                icon: const Icon(Icons.refresh, color: Colors.orange),
                tooltip: 'Regenerate',
                onPressed: onRegenerate,
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline, color: Colors.grey),
                tooltip: 'Delete',
                onPressed: onDelete,
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _formatDate(String isoDate) {
    if (isoDate.isEmpty) return '';
    try {
      final dt = DateTime.parse(isoDate);
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return isoDate;
    }
  }
}
