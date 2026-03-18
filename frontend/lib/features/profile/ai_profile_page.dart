import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/api/api_client.dart';
import '../chat/chat_page.dart';
import 'post_detail_page.dart';

class AIProfilePage extends StatefulWidget {
  final int aiId;
  final String aiName;

  const AIProfilePage({
    super.key,
    required this.aiId,
    required this.aiName,
  });

  @override
  State<AIProfilePage> createState() => _AIProfilePageState();
}

class _AIProfilePageState extends State<AIProfilePage> {
  Map<String, dynamic>? _profile;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  Future<void> _loadProfile() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await ApiClient.get('/api/ai/profile/${widget.aiId}');
      setState(() => _profile = data);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _openChat() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ChatPage(
          aiId: widget.aiId,
          aiName: _profile?['name'] ?? widget.aiName,
        ),
      ),
    );
  }

  void _openPostDetail(Map<String, dynamic> post) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => PostDetailPage(
          post: post,
          aiName: _profile?['name'] ?? widget.aiName,
          aiAvatar: _profile?['avatar_url'] ?? '',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: Text(
          _profile?['name'] ?? widget.aiName,
          style: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 18),
        ),
        centerTitle: false,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text('Failed to load profile',
                          style: GoogleFonts.inter(color: Colors.grey)),
                      const SizedBox(height: 8),
                      TextButton(
                          onPressed: _loadProfile,
                          child: const Text('Retry')),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _loadProfile,
                  child: _buildProfileContent(isDark),
                ),
    );
  }

  Widget _buildProfileContent(bool isDark) {
    final profile = _profile!;
    final posts = (profile['posts'] as List<dynamic>?) ?? [];
    final name = profile['name'] as String? ?? '';
    final bio = profile['bio'] as String? ?? '';
    final profession = profile['profession'] as String? ?? '';
    final statusLabel = profile['status_label'] as String? ?? '';
    final postCount = profile['post_count'] as int? ?? 0;

    return CustomScrollView(
      slivers: [
        // Profile header section
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Top row: avatar + stats
                Row(
                  children: [
                    // Avatar
                    CircleAvatar(
                      radius: 42,
                      backgroundColor: Colors.grey[300],
                      child: Text(
                        name.isNotEmpty ? name[0] : 'A',
                        style: GoogleFonts.inter(
                          fontSize: 32,
                          fontWeight: FontWeight.w600,
                          color: Colors.grey[700],
                        ),
                      ),
                    ),
                    const SizedBox(width: 24),
                    // Stats
                    Expanded(
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                        children: [
                          _buildStatColumn('$postCount', 'Posts'),
                          _buildStatColumn('--', 'Followers'),
                          _buildStatColumn('--', 'Following'),
                        ],
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 14),

                // Name + profession
                Text(
                  name,
                  style: GoogleFonts.inter(
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                  ),
                ),
                if (profession.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      profession,
                      style: GoogleFonts.inter(
                        fontSize: 13,
                        color: Colors.grey[600],
                      ),
                    ),
                  ),

                // Bio
                if (bio.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      bio,
                      style: GoogleFonts.inter(fontSize: 14),
                    ),
                  ),

                // Status label
                if (statusLabel.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: isDark
                            ? Colors.green.withValues(alpha: 0.2)
                            : Colors.green.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 7,
                            height: 7,
                            decoration: const BoxDecoration(
                              color: Colors.green,
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            statusLabel,
                            style: GoogleFonts.inter(
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: Colors.green[700],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),

                const SizedBox(height: 14),

                // Message button
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: _openChat,
                    style: OutlinedButton.styleFrom(
                      side: BorderSide(
                        color: isDark ? Colors.grey[600]! : Colors.grey[350]!,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      padding: const EdgeInsets.symmetric(vertical: 8),
                    ),
                    child: Text(
                      'Message',
                      style: GoogleFonts.inter(
                        fontWeight: FontWeight.w600,
                        fontSize: 14,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),

        // Divider before grid
        SliverToBoxAdapter(
          child: Divider(
              height: 1,
              color: isDark ? Colors.grey[800] : Colors.grey[300]),
        ),

        // Grid icon tab indicator
        SliverToBoxAdapter(
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 10),
            alignment: Alignment.center,
            child: Icon(
              Icons.grid_on,
              size: 24,
              color: isDark ? Colors.white : Colors.black,
            ),
          ),
        ),

        // Image grid
        posts.isEmpty
            ? SliverFillRemaining(
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.camera_alt_outlined,
                          size: 48, color: Colors.grey[400]),
                      const SizedBox(height: 12),
                      Text(
                        'No posts yet',
                        style: GoogleFonts.inter(
                          fontSize: 16,
                          color: Colors.grey[500],
                        ),
                      ),
                    ],
                  ),
                ),
              )
            : SliverGrid(
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 3,
                  mainAxisSpacing: 2,
                  crossAxisSpacing: 2,
                ),
                delegate: SliverChildBuilderDelegate(
                  (context, index) {
                    final post = posts[index] as Map<String, dynamic>;
                    final mediaUrl = post['media_url'] as String? ?? '';
                    final isLocked = post['is_locked'] == true;

                    // Locked close-friend content placeholder
                    if (isLocked) {
                      return GestureDetector(
                        onTap: () =>
                            ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content:
                                Text('Raise intimacy to Lv.6 to unlock'),
                          ),
                        ),
                        child: Container(
                          color: isDark
                              ? const Color(0xFF1A1A1A)
                              : Colors.grey[300],
                          child: Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.lock,
                                    color: isDark
                                        ? Colors.white54
                                        : Colors.grey[600],
                                    size: 28),
                                const SizedBox(height: 4),
                                Text(
                                  'Close friend',
                                  style: GoogleFonts.inter(
                                    fontSize: 11,
                                    color: isDark
                                        ? Colors.white54
                                        : Colors.grey[600],
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    }

                    return GestureDetector(
                      onTap: () => _openPostDetail(post),
                      child: mediaUrl.isNotEmpty
                          ? Image.network(
                              ApiClient.proxyImageUrl(mediaUrl),
                              fit: BoxFit.cover,
                              loadingBuilder: (context, child, progress) {
                                if (progress == null) return child;
                                return Container(
                                  color: isDark
                                      ? const Color(0xFF1A1A1A)
                                      : const Color(0xFFF0F0F0),
                                  child: Center(
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: Colors.grey[400],
                                      value: progress.expectedTotalBytes != null
                                          ? progress.cumulativeBytesLoaded /
                                              progress.expectedTotalBytes!
                                          : null,
                                    ),
                                  ),
                                );
                              },
                              errorBuilder: (context, error, stack) =>
                                  Container(
                                color: isDark
                                    ? const Color(0xFF1A1A1A)
                                    : const Color(0xFFF0F0F0),
                                child: Icon(Icons.broken_image_outlined,
                                    color: Colors.grey[400]),
                              ),
                            )
                          : Container(
                              color: isDark
                                  ? const Color(0xFF1A1A1A)
                                  : const Color(0xFFF0F0F0),
                              child: Center(
                                child: Icon(Icons.image_outlined,
                                    color: Colors.grey[400]),
                              ),
                            ),
                    );
                  },
                  childCount: posts.length,
                ),
              ),
      ],
    );
  }

  Widget _buildStatColumn(String count, String label) {
    return Column(
      children: [
        Text(
          count,
          style: GoogleFonts.inter(
            fontWeight: FontWeight.w700,
            fontSize: 17,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: GoogleFonts.inter(
            fontSize: 13,
            color: Colors.grey[600],
          ),
        ),
      ],
    );
  }
}
