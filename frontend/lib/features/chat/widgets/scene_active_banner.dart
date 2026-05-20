/// Active scene banner widget for SoulPulse chat page.
///
/// Displays a small banner at the top of the chat when a scene is active.
/// Shows: scene name, messages remaining, mood preset icon.
/// Provides an "Exit" button to abandon the scene early.

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Banner widget indicating an active scene in chat.
///
/// Place at the top of the chat message area. Provides scene context
/// and a way to exit the scene early.
class SceneActiveBanner extends StatelessWidget {
  /// Name of the active scene
  final String sceneName;

  /// Number of messages remaining in the scene
  final int messagesRemaining;

  /// Mood preset identifier (for tint color)
  final String? moodPreset;

  /// Callback when user taps exit
  final VoidCallback onExit;

  const SceneActiveBanner({
    super.key,
    required this.sceneName,
    required this.messagesRemaining,
    this.moodPreset,
    required this.onExit,
  });

  /// Get tint color based on mood preset
  Color _getMoodColor() {
    switch (moodPreset) {
      case 'romantic':
        return const Color(0xFFB76E79);
      case 'melancholy':
        return const Color(0xFF6B4F8A);
      case 'excited':
        return const Color(0xFFD4A84B);
      case 'calm':
        return const Color(0xFF4A8A5E);
      case 'tense':
        return const Color(0xFFB85A3A);
      case 'mysterious':
        return const Color(0xFF3D5A73);
      default:
        return const Color(0xFF9C8AA5);
    }
  }

  /// Get mood icon based on preset
  IconData _getMoodIcon() {
    switch (moodPreset) {
      case 'romantic':
        return Icons.favorite_border;
      case 'melancholy':
        return Icons.water_drop_outlined;
      case 'excited':
        return Icons.local_fire_department_outlined;
      case 'calm':
        return Icons.spa_outlined;
      case 'tense':
        return Icons.bolt_outlined;
      case 'mysterious':
        return Icons.visibility_outlined;
      default:
        return Icons.auto_stories_outlined;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final moodColor = _getMoodColor();

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: moodColor.withOpacity(isDark ? 0.15 : 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: moodColor.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Row(
        children: [
          // Mood icon
          Icon(
            _getMoodIcon(),
            size: 18,
            color: moodColor,
          ),
          const SizedBox(width: 10),

          // Scene name & remaining
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  sceneName,
                  style: GoogleFonts.inter(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: theme.colorScheme.onSurface,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  '剩余 $messagesRemaining 条对话',
                  style: GoogleFonts.inter(
                    fontSize: 11,
                    color: theme.colorScheme.onSurface.withOpacity(0.6),
                  ),
                ),
              ],
            ),
          ),

          // Exit button
          GestureDetector(
            onTap: () => _showExitConfirmation(context),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: theme.colorScheme.onSurface.withOpacity(0.08),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                '退出',
                style: GoogleFonts.inter(
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                  color: theme.colorScheme.onSurface.withOpacity(0.7),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _showExitConfirmation(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('退出场景'),
        content: const Text('确定要退出当前场景吗？场景进度将不会保存。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              onExit();
            },
            child: Text(
              '退出',
              style: TextStyle(color: Theme.of(ctx).colorScheme.error),
            ),
          ),
        ],
      ),
    );
  }
}
