/// Scene start confirmation dialog for SoulPulse.
///
/// Shows a modal dialog before entering a scene, displaying:
/// - Scene name and setting description
/// - CG background preview (if available)
/// - Cost information and intimacy check
/// - "进入场景" action button

import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/api_client.dart';
import 'scene_models.dart';
import 'scene_service.dart';

/// Confirmation dialog shown before starting a scene.
class SceneStartDialog extends StatefulWidget {
  final Scene scene;
  final int personaId;
  final String personaName;

  const SceneStartDialog({
    super.key,
    required this.scene,
    required this.personaId,
    required this.personaName,
  });

  @override
  State<SceneStartDialog> createState() => _SceneStartDialogState();
}

class _SceneStartDialogState extends State<SceneStartDialog> {
  bool _starting = false;

  Future<void> _startScene() async {
    setState(() => _starting = true);

    try {
      await SceneService.startScene(widget.personaId, widget.scene.id);

      if (mounted) {
        Navigator.of(context).pop(true); // pop with success result

        // Navigate to chat page with active scene
        context.push(
          '/chat/${widget.personaId}?name=${Uri.encodeComponent(widget.personaName)}',
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => _starting = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('进入场景失败: ${e.toString().replaceFirst("Exception: ", "")}'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final scene = widget.scene;
    final hasCg = scene.sceneCgUrl != null && scene.sceneCgUrl!.isNotEmpty;

    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 40),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 380),
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF22223A) : Colors.white,
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.2),
              blurRadius: 24,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // CG background or gradient header
              _buildHeader(theme, isDark, hasCg),

              // Content
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Scene name
                    Text(
                      scene.sceneName,
                      style: GoogleFonts.playfairDisplay(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 10),

                    // Setting description
                    Text(
                      scene.settingDescription,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurface.withOpacity(0.7),
                        height: 1.5,
                      ),
                      maxLines: 4,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 16),

                    // Info chips
                    Wrap(
                      spacing: 10,
                      runSpacing: 8,
                      children: [
                        _InfoChip(
                          icon: Icons.chat_bubble_outline,
                          label: '${scene.maxMessages}条对话',
                          color: theme.colorScheme.primary,
                        ),
                        if (scene.moodPreset != null)
                          _InfoChip(
                            icon: Icons.mood,
                            label: scene.moodPreset!,
                            color: theme.colorScheme.secondary,
                          ),
                        if (scene.isPaid)
                          _InfoChip(
                            icon: Icons.diamond_outlined,
                            label: '${scene.unlockCost} 宝石',
                            color: const Color(0xFFD4A84B),
                          ),
                      ],
                    ),

                    const SizedBox(height: 20),

                    // Action button
                    SizedBox(
                      width: double.infinity,
                      height: 48,
                      child: ElevatedButton(
                        onPressed: _starting ? null : _startScene,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: theme.colorScheme.primary,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14),
                          ),
                          elevation: 0,
                        ),
                        child: _starting
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : Text(
                                '进入场景',
                                style: GoogleFonts.inter(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                      ),
                    ),

                    // Cancel button
                    const SizedBox(height: 10),
                    Center(
                      child: TextButton(
                        onPressed: () => Navigator.of(context).pop(false),
                        child: Text(
                          '取消',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color:
                                theme.colorScheme.onSurface.withOpacity(0.5),
                          ),
                        ),
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

  Widget _buildHeader(ThemeData theme, bool isDark, bool hasCg) {
    if (hasCg) {
      return Stack(
        children: [
          CachedNetworkImage(
            imageUrl: ApiClient.proxyImageUrl(widget.scene.sceneCgUrl!),
            height: 160,
            width: double.infinity,
            fit: BoxFit.cover,
            placeholder: (_, __) => Container(
              height: 160,
              color: isDark
                  ? const Color(0xFF1A1A2E)
                  : const Color(0xFFF5F4F0),
            ),
            errorWidget: (_, __, ___) => Container(
              height: 160,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    theme.colorScheme.primary.withOpacity(0.3),
                    theme.colorScheme.secondary.withOpacity(0.3),
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
              ),
            ),
          ),
          // Gradient overlay for readability
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: Container(
              height: 60,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    Colors.transparent,
                    (isDark ? const Color(0xFF22223A) : Colors.white)
                        .withOpacity(0.9),
                  ],
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                ),
              ),
            ),
          ),
        ],
      );
    }

    // Fallback gradient header
    return Container(
      height: 80,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            theme.colorScheme.primary.withOpacity(0.15),
            theme.colorScheme.secondary.withOpacity(0.08),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Center(
        child: Icon(
          Icons.auto_stories,
          size: 36,
          color: theme.colorScheme.primary.withOpacity(0.6),
        ),
      ),
    );
  }
}

/// Small chip for displaying scene metadata.
class _InfoChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;

  const _InfoChip({
    required this.icon,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 5),
          Text(
            label,
            style: GoogleFonts.inter(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}
