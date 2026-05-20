// ============================================================================
// MediaMessageBubble — image / voice / video bubbles for the chat timeline
// ============================================================================
//
// Routing logic:
//  • voiceUrl present          → VoiceBubble  (audioplayers playback)
//  • mediaType == "image"      → ImageBubble  (tap to open ImageViewer)
//  • mediaType == "video"      → VideoBubble  (tap to open full-screen player)
//
// All variants respect the isUser flag for left/right alignment and use the
// character colour palette for theming.
// ============================================================================

import 'dart:async';
import 'dart:math' as math;
import 'package:audioplayers/audioplayers.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'image_viewer.dart';
import '../../../core/theme/character_theme.dart';

/// Top-level router — picks the right bubble variant based on message fields.
class MediaMessageBubble extends StatelessWidget {
  /// Uploaded media URL (image or video preview).
  final String? mediaUrl;

  /// "image", "voice", or "video".
  final String? mediaType;

  /// URL of a voice clip (either user's recording or AI voice reply).
  final String? voiceUrl;

  /// Approximate duration of the voice clip in seconds.
  final int? voiceDuration;

  /// Whether the message was sent by the local user.
  final bool isUser;

  /// Character colour palette for theming AI bubbles.
  final CharacterColors characterColors;

  /// True when the app is in dark mode.
  final bool isDark;

  const MediaMessageBubble({
    super.key,
    this.mediaUrl,
    this.mediaType,
    this.voiceUrl,
    this.voiceDuration,
    required this.isUser,
    required this.characterColors,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    // Voice takes priority — both user recordings and AI voice replies
    if (voiceUrl != null && voiceUrl!.isNotEmpty) {
      return _VoiceBubble(
        voiceUrl: voiceUrl!,
        duration: voiceDuration ?? 0,
        isUser: isUser,
        characterColors: characterColors,
        isDark: isDark,
      );
    }

    if (mediaType == 'image' && mediaUrl != null && mediaUrl!.isNotEmpty) {
      return _ImageBubble(
        imageUrl: mediaUrl!,
        isUser: isUser,
        characterColors: characterColors,
        isDark: isDark,
      );
    }

    if (mediaType == 'video' && mediaUrl != null && mediaUrl!.isNotEmpty) {
      return _VideoBubble(
        videoUrl: mediaUrl!,
        isUser: isUser,
        characterColors: characterColors,
        isDark: isDark,
      );
    }

    return const SizedBox.shrink();
  }
}

// ============================================================================
// Image bubble
// ============================================================================

class _ImageBubble extends StatelessWidget {
  final String imageUrl;
  final bool isUser;
  final CharacterColors characterColors;
  final bool isDark;

  const _ImageBubble({
    required this.imageUrl,
    required this.isUser,
    required this.characterColors,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    final heroTag = 'img_${imageUrl.hashCode}';

    return Align(
      alignment:
          isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: GestureDetector(
        onTap: () =>
            ImageViewer.show(context, imageUrl: imageUrl, heroTag: heroTag),
        child: Hero(
          tag: heroTag,
          child: Container(
            margin: const EdgeInsets.only(bottom: 8),
            constraints: BoxConstraints(
              maxWidth: MediaQuery.of(context).size.width * 0.65,
              maxHeight: 280,
            ),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.only(
                topLeft: const Radius.circular(16),
                topRight: const Radius.circular(16),
                bottomLeft: Radius.circular(isUser ? 16 : 4),
                bottomRight: Radius.circular(isUser ? 4 : 16),
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.12),
                  blurRadius: 8,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            clipBehavior: Clip.antiAlias,
            child: Stack(
              fit: StackFit.passthrough,
              children: [
                CachedNetworkImage(
                  imageUrl: imageUrl,
                  fit: BoxFit.cover,
                  placeholder: (_, __) => Container(
                    width: 200,
                    height: 160,
                    color: Colors.grey.withValues(alpha: 0.18),
                    child: const Center(
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  ),
                  errorWidget: (_, __, ___) => Container(
                    width: 200,
                    height: 160,
                    color: Colors.grey.withValues(alpha: 0.18),
                    child: const Icon(
                        Icons.broken_image_outlined,
                        color: Colors.grey),
                  ),
                ),
                // Tap-to-zoom hint overlay (bottom-right corner)
                Positioned(
                  right: 6,
                  bottom: 6,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.35),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: const Icon(
                      Icons.zoom_out_map_rounded,
                      color: Colors.white70,
                      size: 13,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================================
// Voice bubble
// ============================================================================

class _VoiceBubble extends StatefulWidget {
  final String voiceUrl;
  final int duration;
  final bool isUser;
  final CharacterColors characterColors;
  final bool isDark;

  const _VoiceBubble({
    required this.voiceUrl,
    required this.duration,
    required this.isUser,
    required this.characterColors,
    required this.isDark,
  });

  @override
  State<_VoiceBubble> createState() => _VoiceBubbleState();
}

class _VoiceBubbleState extends State<_VoiceBubble>
    with SingleTickerProviderStateMixin {
  final AudioPlayer _player = AudioPlayer();
  StreamSubscription? _posSub;
  StreamSubscription? _stateSub;
  StreamSubscription? _durSub;

  bool _playing = false;
  int _positionSecs = 0;
  int _totalSecs = 0;

  late final AnimationController _waveCtrl;

  @override
  void initState() {
    super.initState();
    _totalSecs = widget.duration;

    _waveCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );

    _posSub = _player.onPositionChanged.listen((d) {
      if (mounted) setState(() => _positionSecs = d.inSeconds);
    });

    _durSub = _player.onDurationChanged.listen((d) {
      if (mounted) setState(() => _totalSecs = d.inSeconds);
    });

    _stateSub = _player.onPlayerStateChanged.listen((s) {
      if (!mounted) return;
      setState(() => _playing = s == PlayerState.playing);
      if (s == PlayerState.playing) {
        _waveCtrl.repeat();
      } else {
        _waveCtrl
          ..stop()
          ..reset();
        if (s == PlayerState.completed) {
          setState(() => _positionSecs = 0);
        }
      }
    });
  }

  @override
  void dispose() {
    _posSub?.cancel();
    _durSub?.cancel();
    _stateSub?.cancel();
    _waveCtrl.dispose();
    _player.dispose();
    super.dispose();
  }

  Future<void> _toggle() async {
    if (_playing) {
      await _player.pause();
    } else {
      await _player.play(UrlSource(widget.voiceUrl));
    }
  }

  String _fmt(int s) {
    final m = s ~/ 60;
    final sec = s % 60;
    return '${m.toString().padLeft(2, '0')}:${sec.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final bgColor = widget.isUser
        ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.12)
        : widget.characterColors.primary
            .withValues(alpha: widget.isDark ? 0.14 : 0.09);
    final accentColor = widget.isUser
        ? Theme.of(context).colorScheme.primary
        : widget.characterColors.primary;
    final displayTotal =
        _totalSecs > 0 ? _totalSecs : widget.duration;

    return Align(
      alignment:
          widget.isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints: const BoxConstraints(minWidth: 155, maxWidth: 255),
        decoration: BoxDecoration(
          color: bgColor,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(18),
            topRight: const Radius.circular(18),
            bottomLeft: Radius.circular(widget.isUser ? 18 : 4),
            bottomRight: Radius.circular(widget.isUser ? 4 : 18),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Play / Pause button
            GestureDetector(
              onTap: _toggle,
              child: Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: accentColor,
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  _playing ? Icons.pause_rounded : Icons.play_arrow_rounded,
                  color: Colors.white,
                  size: 20,
                ),
              ),
            ),

            const SizedBox(width: 10),

            // Waveform + duration
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Animated waveform bars
                  AnimatedBuilder(
                    animation: _waveCtrl,
                    builder: (_, __) {
                      return Row(
                        children: List.generate(14, (i) {
                          final phase = _waveCtrl.value * 2 * math.pi +
                              i * (math.pi / 5.0);
                          final h = _playing
                              ? 3.0 + 8.0 * (0.5 + 0.5 * math.sin(phase))
                              : 3.5;
                          return AnimatedContainer(
                            duration: const Duration(milliseconds: 60),
                            margin: const EdgeInsets.symmetric(horizontal: 1),
                            width: 3,
                            height: h,
                            decoration: BoxDecoration(
                              color: accentColor.withValues(
                                  alpha: _playing ? 0.85 : 0.4),
                              borderRadius: BorderRadius.circular(1.5),
                            ),
                          );
                        }),
                      );
                    },
                  ),

                  const SizedBox(height: 4),

                  // Duration text
                  Text(
                    _playing
                        ? '${_fmt(_positionSecs)} / ${_fmt(displayTotal)}'
                        : _fmt(displayTotal),
                    style: GoogleFonts.inter(
                      fontSize: 11,
                      color: accentColor.withValues(alpha: 0.75),
                    ),
                  ),
                ],
              ),
            ),

            // Speaker icon for AI voice replies (non-user only)
            if (!widget.isUser) ...[
              const SizedBox(width: 6),
              Icon(
                Icons.volume_up_rounded,
                size: 14,
                color: accentColor.withValues(alpha: 0.55),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ============================================================================
// Video bubble
// ============================================================================

class _VideoBubble extends StatelessWidget {
  final String videoUrl;
  final bool isUser;
  final CharacterColors characterColors;
  final bool isDark;

  const _VideoBubble({
    required this.videoUrl,
    required this.isUser,
    required this.characterColors,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment:
          isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: GestureDetector(
        onTap: () => _openPlayer(context),
        child: Container(
          margin: const EdgeInsets.only(bottom: 8),
          width: 210,
          height: 148,
          decoration: BoxDecoration(
            color: isDark ? const Color(0xFF1A1A2E) : const Color(0xFF111122),
            borderRadius: BorderRadius.only(
              topLeft: const Radius.circular(16),
              topRight: const Radius.circular(16),
              bottomLeft: Radius.circular(isUser ? 16 : 4),
              bottomRight: Radius.circular(isUser ? 4 : 16),
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.18),
                blurRadius: 8,
                offset: const Offset(0, 3),
              ),
            ],
          ),
          clipBehavior: Clip.antiAlias,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Background shimmer / gradient
              Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      characterColors.primary.withValues(alpha: 0.15),
                      Colors.black.withValues(alpha: 0.4),
                    ],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                ),
              ),

              // Play button
              Container(
                width: 52,
                height: 52,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white.withValues(alpha: 0.88),
                  boxShadow: [
                    BoxShadow(
                      color: characterColors.primary.withValues(alpha: 0.3),
                      blurRadius: 12,
                    ),
                  ],
                ),
                child: Icon(
                  Icons.play_arrow_rounded,
                  size: 32,
                  color: characterColors.primary,
                ),
              ),

              // Bottom label
              Positioned(
                bottom: 8,
                left: 10,
                right: 10,
                child: Row(
                  children: [
                    Icon(
                      Icons.videocam_rounded,
                      size: 13,
                      color: Colors.white.withValues(alpha: 0.75),
                    ),
                    const SizedBox(width: 4),
                    Text(
                      'Video',
                      style: GoogleFonts.inter(
                        fontSize: 11,
                        color: Colors.white.withValues(alpha: 0.75),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _openPlayer(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _VideoPlayerSheet(
        videoUrl: videoUrl,
        characterColors: characterColors,
      ),
    );
  }
}

// ─── minimal video player sheet ───────────────────────────────────────────

class _VideoPlayerSheet extends StatelessWidget {
  final String videoUrl;
  final CharacterColors characterColors;

  const _VideoPlayerSheet({
    required this.videoUrl,
    required this.characterColors,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.55,
      decoration: const BoxDecoration(
        color: Colors.black87,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        children: [
          // Handle bar
          Container(
            margin: const EdgeInsets.only(top: 10, bottom: 4),
            width: 36,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.white38,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          // Header
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Video',
                  style: GoogleFonts.inter(
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                      fontSize: 16),
                ),
                IconButton(
                  icon: const Icon(Icons.close, color: Colors.white),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ],
            ),
          ),
          // Player area
          Expanded(
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 72,
                    height: 72,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: characterColors.primary.withValues(alpha: 0.2),
                    ),
                    child: Icon(
                      Icons.videocam_rounded,
                      color: characterColors.primary,
                      size: 36,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    '视频播放功能即将上线',
                    style: GoogleFonts.inter(
                        color: Colors.white70, fontSize: 14),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    videoUrl.length > 50
                        ? '${videoUrl.substring(0, 50)}…'
                        : videoUrl,
                    style: GoogleFonts.inter(
                        color: Colors.white38, fontSize: 11),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
