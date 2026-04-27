import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:video_player/video_player.dart';
import '../../core/api/api_client.dart';

class StoryPlayerPage extends StatefulWidget {
  final List<dynamic> stories;
  final int initialIndex;
  final String aiName;
  final int aiId;

  const StoryPlayerPage({
    super.key,
    required this.stories,
    this.initialIndex = 0,
    required this.aiName,
    required this.aiId,
  });

  @override
  State<StoryPlayerPage> createState() => _StoryPlayerPageState();
}

class _StoryPlayerPageState extends State<StoryPlayerPage> {
  late int _currentIndex;
  VideoPlayerController? _controller;
  bool _initialized = false;
  bool _isImage = false;
  String? _imageUrl;
  String? _error;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    _loadMedia();
  }

  bool _urlIsImage(String url) {
    final lower = url.toLowerCase();
    return lower.endsWith('.png') ||
        lower.endsWith('.jpg') ||
        lower.endsWith('.jpeg') ||
        lower.endsWith('.gif') ||
        lower.endsWith('.webp');
  }

  Future<void> _loadMedia() async {
    setState(() {
      _initialized = false;
      _isImage = false;
      _imageUrl = null;
      _error = null;
    });

    _controller?.dispose();
    _controller = null;

    final story = widget.stories[_currentIndex];
    final mediaUrl =
        ApiClient.proxyImageUrl(story['video_url'] as String? ?? '');

    // Mark story as viewed
    final storyId = story['id'] as int?;
    if (storyId != null) {
      ApiClient.post('/api/feed/stories/$storyId/view', {})
          .catchError((_) => <String, dynamic>{});
    }

    if (mediaUrl.isEmpty) {
      setState(() => _error = 'No media available');
      return;
    }

    if (_urlIsImage(mediaUrl)) {
      setState(() {
        _isImage = true;
        _imageUrl = mediaUrl;
        _initialized = true;
      });
      Future.delayed(const Duration(seconds: 5), () {
        if (mounted && _currentIndex == widget.stories.indexOf(story)) {
          _nextStory();
        }
      });
      return;
    }

    final controller = VideoPlayerController.networkUrl(Uri.parse(mediaUrl));
    try {
      await controller.initialize();
      controller.setLooping(true);
      await controller.play();
      if (mounted) {
        setState(() {
          _controller = controller;
          _initialized = true;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = 'Failed to load video');
    }
  }

  void _nextStory() {
    if (_currentIndex < widget.stories.length - 1) {
      _currentIndex++;
      _loadMedia();
    } else {
      context.pop();
    }
  }

  void _prevStory() {
    if (_currentIndex > 0) {
      _currentIndex--;
      _loadMedia();
    }
  }

  void _openChat() {
    context.pop();
    final aiName = Uri.encodeComponent(widget.aiName);
    context.push('/chat/${widget.aiId}?name=$aiName');
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final story = widget.stories[_currentIndex];
    final caption = story['caption'] as String? ?? '';

    return Scaffold(
      backgroundColor: Colors.black,
      body: GestureDetector(
        onTapUp: (details) {
          final screenWidth = MediaQuery.of(context).size.width;
          if (details.globalPosition.dx < screenWidth / 3) {
            _prevStory();
          } else {
            _nextStory();
          }
        },
        onVerticalDragEnd: (details) {
          if (details.primaryVelocity != null &&
              details.primaryVelocity! > 300) {
            context.pop();
          }
        },
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (_initialized && _isImage && _imageUrl != null)
              Center(
                child: CachedNetworkImage(
                  imageUrl: _imageUrl!,
                  fit: BoxFit.cover,
                  width: double.infinity,
                  height: double.infinity,
                  errorWidget: (_, __, ___) => const Center(
                    child: Icon(Icons.broken_image_outlined,
                        size: 48, color: Colors.white54),
                  ),
                ),
              )
            else if (_initialized && _controller != null)
              Center(
                child: AspectRatio(
                  aspectRatio: _controller!.value.aspectRatio,
                  child: VideoPlayer(_controller!),
                ),
              )
            else if (_error != null)
              Center(
                child: Text(_error!,
                    style:
                        GoogleFonts.inter(color: Colors.white54, fontSize: 14)),
              )
            else
              const Center(
                  child: CircularProgressIndicator(color: Colors.white)),

            // Progress bars
            if (widget.stories.length > 1)
              Positioned(
                top: MediaQuery.of(context).padding.top + 2,
                left: 12,
                right: 12,
                child: Row(
                  children: List.generate(widget.stories.length, (i) {
                    return Expanded(
                      child: Container(
                        height: 2,
                        margin: const EdgeInsets.symmetric(horizontal: 2),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(1),
                          color: i <= _currentIndex
                              ? Colors.white
                              : Colors.white.withValues(alpha: 0.3),
                        ),
                      ),
                    );
                  }),
                ),
              ),

            // Top bar
            Positioned(
              top: MediaQuery.of(context).padding.top + 8,
              left: 12,
              right: 12,
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 16,
                    backgroundColor: Colors.grey[700],
                    child: Text(
                      widget.aiName.isNotEmpty ? widget.aiName[0] : 'A',
                      style: GoogleFonts.inter(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: Colors.white),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(widget.aiName,
                        style: GoogleFonts.inter(
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                            fontSize: 14)),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.white),
                    onPressed: () => context.pop(),
                  ),
                ],
              ),
            ),

            // Bottom caption + DM
            Positioned(
              bottom: MediaQuery.of(context).padding.bottom + 16,
              left: 16,
              right: 16,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (caption.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(
                        caption,
                        style: GoogleFonts.inter(
                          color: Colors.white,
                          fontSize: 15,
                          shadows: [
                            const Shadow(blurRadius: 8, color: Colors.black54)
                          ],
                        ),
                      ),
                    ),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _openChat,
                      icon: const Icon(Icons.chat_bubble_outline,
                          size: 18, color: Colors.white),
                      label: Text('Send message',
                          style: GoogleFonts.inter(
                              color: Colors.white,
                              fontWeight: FontWeight.w500)),
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: Colors.white54),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(24)),
                        padding: const EdgeInsets.symmetric(vertical: 10),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
