import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/api/api_client.dart';
import '../../core/theme/character_theme.dart';

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
  Map<String, dynamic>? _emotion;
  bool _loading = true;
  String? _error;
  bool _followLoading = false;

  @override
  void initState() {
    super.initState();
    _loadProfile();
    _loadEmotion();
  }

  Future<void> _loadProfile() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await ApiClient.get('/api/ai/profile/${widget.aiId}',
          useCache: false);
      setState(() => _profile = data);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadEmotion() async {
    try {
      final data = await ApiClient.get('/api/ai/emotion/${widget.aiId}');
      if (mounted) setState(() => _emotion = data);
    } catch (_) {}
  }

  Future<void> _toggleFollow() async {
    if (_followLoading || _profile == null) return;
    setState(() => _followLoading = true);

    final isFollowing = _profile!['is_following'] == true;
    // Optimistic update
    setState(() {
      _profile!['is_following'] = !isFollowing;
      _profile!['follower_count'] =
          ((_profile!['follower_count'] as int?) ?? 0) + (isFollowing ? -1 : 1);
    });

    try {
      if (isFollowing) {
        await ApiClient.delete('/api/ai/${widget.aiId}/follow');
      } else {
        await ApiClient.post('/api/ai/${widget.aiId}/follow', {});
      }
      HapticFeedback.lightImpact();
    } catch (_) {
      // Revert
      setState(() {
        _profile!['is_following'] = isFollowing;
        _profile!['follower_count'] =
            ((_profile!['follower_count'] as int?) ?? 0) +
                (isFollowing ? 1 : -1);
      });
    } finally {
      if (mounted) setState(() => _followLoading = false);
    }
  }

  void _openChat() async {
    final aiName = Uri.encodeComponent(_profile?['name'] ?? widget.aiName);
    await context.push('/chat/${widget.aiId}?name=$aiName');
    // Refresh profile on return (intimacy may change)
    if (mounted) _loadProfile();
  }

  void _openPostDetail(Map<String, dynamic> post) async {
    await context.push('/post-detail', extra: {
      'post': post,
      'aiName': post['ai_name'] ?? _profile?['name'] ?? widget.aiName,
      'aiAvatar': ApiClient.proxyImageUrl(
          (post['ai_avatar'] ?? _profile?['avatar_url'] ?? '') as String),
    });
    // Refresh profile when returning from post detail (like counts may change)
    if (mounted) _loadProfile();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.pop(),
        ),
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
                          onPressed: _loadProfile, child: const Text('Retry')),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: () async {
                    await Future.wait([_loadProfile(), _loadEmotion()]);
                  },
                  child: _buildProfileContent(),
                ),
    );
  }

  Widget _buildProfileContent() {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final profile = _profile!;
    final posts = (profile['posts'] as List<dynamic>?) ?? [];
    final name = profile['name'] as String? ?? '';
    final bio = profile['bio'] as String? ?? '';
    final profession = profile['profession'] as String? ?? '';
    final statusLabel = profile['status_label'] as String? ?? '';
    final postCount = profile['post_count'] as int? ?? 0;
    final followerCount = profile['follower_count'] as int? ?? 0;
    final isFollowing = profile['is_following'] == true;
    final intimacyLevel = profile['intimacy_level'] as String?;
    final intimacyScore = (profile['intimacy_score'] as num?)?.toDouble();
    final avatarUrl =
        ApiClient.proxyImageUrl(profile['avatar_url'] as String? ?? '');

    // Get character-specific colors
    final characterColors = CharacterTheme.getPalette(name);

    return CustomScrollView(
      slivers: [
        // Hero header with gradient
        SliverToBoxAdapter(
          child: Container(
            height: 200,
            width: double.infinity,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  characterColors.getGradient1(
                      isDark ? Brightness.dark : Brightness.light),
                  characterColors.primary,
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
            ),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      _buildProfileAvatar(
                        avatarUrl,
                        name,
                        43,
                        borderColor: Colors.white,
                        borderWidth: 3,
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Text(
                          name,
                          style: Theme.of(context)
                              .textTheme
                              .displaySmall
                              ?.copyWith(color: Colors.white),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),

        // Stats card
        SliverToBoxAdapter(
          child: Container(
            margin: const EdgeInsets.all(16),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surface,
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
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                _buildStatColumn('$postCount', 'Posts'),
                _buildStatColumn('$followerCount', 'Followers'),
                if (intimacyLevel != null)
                  _buildStatColumn(
                    intimacyScore != null
                        ? intimacyScore.toStringAsFixed(1)
                        : '--',
                    'Intimacy',
                  ),
              ],
            ),
          ),
        ),

        // Bio, chips, intimacy, buttons
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (profession.isNotEmpty)
                  Text(
                    profession,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          color: Theme.of(context).colorScheme.primary,
                        ),
                  ),

                // Bio
                if (bio.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      bio,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: Theme.of(context)
                                .colorScheme
                                .onSurface
                                .withValues(alpha: 0.8),
                          ),
                    ),
                  ),

                // Status label + emotion
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: [
                    if (statusLabel.isNotEmpty)
                      _buildChip(
                        icon: Icons.circle,
                        iconSize: 7,
                        iconColor: Colors.green,
                        label: statusLabel,
                        bgColor: isDark
                            ? Colors.green.withValues(alpha: 0.2)
                            : Colors.green.withValues(alpha: 0.1),
                        textColor: Colors.green[700]!,
                      ),
                    if (_emotion != null && _emotion!['mood'] != null)
                      _buildChip(
                        icon: _moodIcon(_emotion!['mood']),
                        iconSize: 14,
                        iconColor: _moodColor(_emotion!['mood']),
                        label: 'Feeling ${_emotion!['mood']}',
                        bgColor: _moodColor(_emotion!['mood'])
                            .withValues(alpha: 0.1),
                        textColor: _moodColor(_emotion!['mood']),
                      ),
                    if (intimacyLevel != null)
                      _buildChip(
                        icon: _intimacyIcon(intimacyLevel),
                        iconSize: 14,
                        iconColor: characterColors.primary,
                        label: intimacyLevel,
                        bgColor: characterColors.primary.withValues(alpha: 0.1),
                        textColor: characterColors.primary,
                      ),
                  ],
                ),

                // Relationship section with progress bar
                if (intimacyScore != null) ...[
                  const SizedBox(height: 16),
                  // Relationship label
                  Row(
                    children: [
                      Icon(
                        _intimacyIcon(intimacyLevel ?? 'Stranger'),
                        size: 16,
                        color: characterColors.primary,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'Relationship: ${intimacyLevel ?? "Stranger"}',
                        style: GoogleFonts.inter(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: characterColors.primary,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  // Progress bar
                  Row(
                    children: [
                      Expanded(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(4),
                          child: LinearProgressIndicator(
                            value: (intimacyScore / 10.0).clamp(0.0, 1.0),
                            minHeight: 6,
                            backgroundColor:
                                isDark ? Colors.grey[800] : Colors.grey[200],
                            valueColor:
                                AlwaysStoppedAnimation(characterColors.primary),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '${intimacyScore.toStringAsFixed(1)} / 10.0',
                        style: GoogleFonts.inter(
                            fontSize: 11, color: Colors.grey[500]),
                      ),
                    ],
                  ),
                ],

                const SizedBox(height: 16),

                // Action buttons: Follow + Message
                Row(
                  children: [
                    Expanded(
                      child: _followLoading
                          ? const Center(
                              child: SizedBox(
                                  height: 20,
                                  width: 20,
                                  child: CircularProgressIndicator(
                                      strokeWidth: 2)),
                            )
                          : isFollowing
                              ? OutlinedButton(
                                  onPressed: _toggleFollow,
                                  style: OutlinedButton.styleFrom(
                                    side: BorderSide(
                                        color: isDark
                                            ? Colors.grey[600]!
                                            : Colors.grey[350]!),
                                    shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(8)),
                                    padding:
                                        const EdgeInsets.symmetric(vertical: 8),
                                  ),
                                  child: Text('Following',
                                      style: GoogleFonts.inter(
                                          fontWeight: FontWeight.w600,
                                          fontSize: 14)),
                                )
                              : ElevatedButton(
                                  onPressed: _toggleFollow,
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor:
                                        Theme.of(context).colorScheme.primary,
                                    foregroundColor: Colors.white,
                                    shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(8)),
                                    padding:
                                        const EdgeInsets.symmetric(vertical: 8),
                                  ),
                                  child: Text('Follow',
                                      style: GoogleFonts.inter(
                                          fontWeight: FontWeight.w600,
                                          fontSize: 14)),
                                ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton(
                        onPressed: _openChat,
                        style: OutlinedButton.styleFrom(
                          side: BorderSide(
                              color: isDark
                                  ? Colors.grey[600]!
                                  : Colors.grey[350]!),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8)),
                          padding: const EdgeInsets.symmetric(vertical: 8),
                        ),
                        child: Text('Message',
                            style: GoogleFonts.inter(
                                fontWeight: FontWeight.w600, fontSize: 14)),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
              ],
            ),
          ),
        ),

        // Divider
        SliverToBoxAdapter(
          child: Divider(
              height: 1, color: isDark ? Colors.grey[800] : Colors.grey[300]),
        ),

        // Grid icon
        SliverToBoxAdapter(
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 10),
            alignment: Alignment.center,
            child: Icon(Icons.grid_on,
                size: 24, color: isDark ? Colors.white : Colors.black),
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
                      Text('No posts yet',
                          style: GoogleFonts.inter(
                              fontSize: 16, color: Colors.grey[500])),
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
                    final mediaUrl = ApiClient.proxyImageUrl(
                        post['media_url'] as String? ?? '');
                    final isLocked = post['is_locked'] == true;

                    if (isLocked) {
                      // Calculate required intimacy to unlock (close friend = 6.0)
                      const unlockThreshold = 6.0;
                      final currentScore = intimacyScore ?? 0.0;
                      final needed =
                          (unlockThreshold - currentScore).clamp(0.0, 10.0);

                      return GestureDetector(
                        onTap: () => ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                              content: Text(
                                  'Raise intimacy by ${needed.toStringAsFixed(1)} to unlock')),
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
                                Text('Close friend',
                                    style: GoogleFonts.inter(
                                        fontSize: 11,
                                        color: isDark
                                            ? Colors.white54
                                            : Colors.grey[600])),
                                Text('+${needed.toStringAsFixed(1)} to unlock',
                                    style: GoogleFonts.inter(
                                        fontSize: 10,
                                        color: characterColors.primary
                                            .withValues(alpha: 0.8))),
                              ],
                            ),
                          ),
                        ),
                      );
                    }

                    return GestureDetector(
                      onTap: () => _openPostDetail(post),
                      child: mediaUrl.isNotEmpty
                          ? CachedNetworkImage(
                              imageUrl: mediaUrl,
                              fit: BoxFit.cover,
                              placeholder: (_, __) => Container(
                                color: isDark
                                    ? const Color(0xFF1A1A1A)
                                    : const Color(0xFFF0F0F0),
                                child: Center(
                                  child: CircularProgressIndicator(
                                      strokeWidth: 2, color: Colors.grey[400]),
                                ),
                              ),
                              errorWidget: (_, __, ___) => Container(
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

  Widget _buildProfileAvatar(
    String url,
    String name,
    double radius, {
    Color? borderColor,
    double borderWidth = 2.5,
  }) {
    final avatar = url.isNotEmpty
        ? CircleAvatar(
            radius: radius - borderWidth,
            backgroundColor: Colors.grey[300],
            child: ClipOval(
              child: CachedNetworkImage(
                imageUrl: url,
                width: (radius - borderWidth) * 2,
                height: (radius - borderWidth) * 2,
                fit: BoxFit.cover,
                errorWidget: (_, __, ___) => Text(
                  name.isNotEmpty ? name[0] : 'A',
                  style: GoogleFonts.inter(
                      fontSize: radius * 0.75,
                      fontWeight: FontWeight.w600,
                      color: Colors.grey[700]),
                ),
              ),
            ),
          )
        : CircleAvatar(
            radius: radius - borderWidth,
            backgroundColor: Colors.grey[300],
            child: Text(
              name.isNotEmpty ? name[0] : 'A',
              style: GoogleFonts.inter(
                  fontSize: radius * 0.75,
                  fontWeight: FontWeight.w600,
                  color: Colors.grey[700]),
            ),
          );

    // Wrap with colored border if borderColor is provided
    if (borderColor != null) {
      return Container(
        padding: EdgeInsets.all(borderWidth / 2),
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: borderColor, width: borderWidth),
        ),
        child: avatar,
      );
    }
    return avatar;
  }

  Widget _buildChip({
    required IconData icon,
    required double iconSize,
    required Color iconColor,
    required String label,
    required Color bgColor,
    required Color textColor,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: iconSize, color: iconColor),
          const SizedBox(width: 6),
          Text(
            label,
            style: GoogleFonts.inter(
                fontSize: 12, fontWeight: FontWeight.w500, color: textColor),
          ),
        ],
      ),
    );
  }

  Widget _buildStatColumn(String count, String label) {
    return Column(
      children: [
        Text(count,
            style:
                GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 17)),
        const SizedBox(height: 2),
        Text(label,
            style: GoogleFonts.inter(fontSize: 13, color: Colors.grey[600])),
      ],
    );
  }

  IconData _moodIcon(String? mood) {
    switch (mood) {
      case 'joyful':
        return Icons.sentiment_very_satisfied;
      case 'good':
        return Icons.sentiment_satisfied;
      case 'neutral':
        return Icons.sentiment_neutral;
      case 'subdued':
        return Icons.sentiment_dissatisfied;
      case 'melancholic':
        return Icons.sentiment_very_dissatisfied;
      default:
        return Icons.sentiment_neutral;
    }
  }

  Color _moodColor(String? mood) {
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
        return Colors.blue;
    }
  }

  IconData _intimacyIcon(String level) {
    switch (level) {
      case 'Soulmate':
        return Icons.favorite;
      case 'Close Friend':
        return Icons.people;
      case 'Friend':
        return Icons.person;
      case 'Acquaintance':
        return Icons.handshake;
      default:
        return Icons.person_outline;
    }
  }
}
