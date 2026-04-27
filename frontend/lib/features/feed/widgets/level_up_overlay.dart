import 'package:flutter/material.dart';
import '../../../core/theme/character_theme.dart';

/// A full-screen celebration overlay that appears when the user
/// reaches a new intimacy level with an AI character.
///
/// Shows confetti-style celebration with the new level announcement.
/// Auto-dismisses after 3 seconds or on tap.
class LevelUpOverlay {
  /// Shows the level-up celebration overlay.
  ///
  /// [context] BuildContext for the overlay
  /// [aiName] The name of the AI character
  /// [newLevel] The new intimacy level achieved (e.g., "Friend")
  /// [theme] The character's color theme
  static void show(
    BuildContext context, {
    required String aiName,
    required String newLevel,
    required CharacterColors theme,
  }) {
    final overlay = Overlay.of(context);
    late OverlayEntry entry;

    entry = OverlayEntry(
      builder: (context) => _LevelUpOverlayWidget(
        aiName: aiName,
        newLevel: newLevel,
        theme: theme,
        onDismiss: () {
          entry.remove();
        },
      ),
    );

    overlay.insert(entry);
  }
}

class _LevelUpOverlayWidget extends StatefulWidget {
  final String aiName;
  final String newLevel;
  final CharacterColors theme;
  final VoidCallback onDismiss;

  const _LevelUpOverlayWidget({
    required this.aiName,
    required this.newLevel,
    required this.theme,
    required this.onDismiss,
  });

  @override
  State<_LevelUpOverlayWidget> createState() => _LevelUpOverlayWidgetState();
}

class _LevelUpOverlayWidgetState extends State<_LevelUpOverlayWidget>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _scaleAnimation;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 400),
    );

    _scaleAnimation = Tween<double>(begin: 0.5, end: 1.0).animate(
      CurvedAnimation(
        parent: _controller,
        curve: Curves.elasticOut,
      ),
    );

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _controller,
        curve: Curves.easeOut,
      ),
    );

    _controller.forward();

    // Auto-dismiss after 3 seconds
    Future.delayed(const Duration(seconds: 3), () {
      if (mounted) {
        widget.onDismiss();
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.onDismiss,
      child: Material(
        color: Colors.transparent,
        child: Container(
          color: Colors.black.withValues(alpha: 0.7),
          child: Center(
            child: AnimatedBuilder(
              animation: _controller,
              builder: (context, child) {
                return Opacity(
                  opacity: _fadeAnimation.value,
                  child: Transform.scale(
                    scale: _scaleAnimation.value,
                    child: child,
                  ),
                );
              },
              child: Container(
                margin: const EdgeInsets.symmetric(horizontal: 32),
                padding: const EdgeInsets.all(32),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      widget.theme.gradient1.withValues(alpha: 0.95),
                      widget.theme.primary.withValues(alpha: 0.95),
                    ],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(24),
                  boxShadow: [
                    BoxShadow(
                      color: widget.theme.primary.withValues(alpha: 0.4),
                      blurRadius: 30,
                      spreadRadius: 5,
                    ),
                  ],
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Celebration emoji
                    const Text(
                      '🎉',
                      style: TextStyle(fontSize: 64),
                    ),
                    const SizedBox(height: 16),
                    // Title
                    Text(
                      'Level Up!',
                      style: TextStyle(
                        color: widget.theme.textOnGradient,
                        fontSize: 28,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 12),
                    // Message
                    RichText(
                      textAlign: TextAlign.center,
                      text: TextSpan(
                        style: TextStyle(
                          color: widget.theme.textOnGradient,
                          fontSize: 18,
                        ),
                        children: [
                          const TextSpan(text: 'You and '),
                          TextSpan(
                            text: widget.aiName,
                            style: const TextStyle(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const TextSpan(text: ' are now\n'),
                          TextSpan(
                            text: widget.newLevel,
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 22,
                              color: widget.theme.accent,
                            ),
                          ),
                          const TextSpan(text: '!'),
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),
                    // Heart icon
                    Icon(
                      Icons.favorite,
                      color: widget.theme.accent,
                      size: 32,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
