// Scene list page for SoulPulse.
//
// Displays all available (and locked) scenes for a given AI persona.
// Features scene cards with type badges, intimacy requirements,
// cost indicators, and tap-to-start functionality.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/api/api_client.dart';
import 'scene_models.dart';
import 'scene_service.dart';
import 'scene_start_dialog.dart';

// ─── Providers ────────────────────────────────────────────────────────────────

/// Provider for scenes list, keyed by persona ID
final scenesProvider =
    FutureProvider.family<List<Scene>, int>((ref, personaId) async {
  return SceneService.getAvailableScenes(personaId);
});

// ─── Page ─────────────────────────────────────────────────────────────────────

/// Page showing all scenes available for a persona.
///
/// Accessed from persona profile or chat menu.
class ScenesPage extends ConsumerWidget {
  final int personaId;
  final String personaName;

  const ScenesPage({
    super.key,
    required this.personaId,
    required this.personaName,
  });

  void _onSceneTap(BuildContext context, Scene scene) {
    if (!scene.isAvailable) {
      // Show lock reason
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            scene.isLockedByIntimacy
                ? '需要亲密度达到 ${scene.requiredIntimacy} 才能解锁'
                : '该场景暂不可用',
          ),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    // Show start dialog
    showDialog(
      context: context,
      builder: (ctx) => SceneStartDialog(
        scene: scene,
        personaId: personaId,
        personaName: personaName,
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final asyncScenes = ref.watch(scenesProvider(personaId));

    return Scaffold(
      appBar: AppBar(
        title: Text(
          '$personaName · 场景',
          style: GoogleFonts.inter(
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      body: asyncScenes.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline,
                  size: 48, color: theme.colorScheme.error),
              const SizedBox(height: 12),
              Text('加载场景失败', style: theme.textTheme.bodyMedium),
              const SizedBox(height: 16),
              TextButton(
                onPressed: () => ref.invalidate(scenesProvider(personaId)),
                child: const Text('重试'),
              ),
            ],
          ),
        ),
        data: (scenes) {
          if (scenes.isEmpty) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.auto_stories_outlined,
                    size: 56,
                    color: theme.colorScheme.primary.withOpacity(0.5),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    '暂无可用场景',
                    style: theme.textTheme.bodyLarge?.copyWith(
                      color:
                          theme.colorScheme.onSurface.withOpacity(0.6),
                    ),
                  ),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(scenesProvider(personaId));
              // Wait for the provider to reload
              await ref.read(scenesProvider(personaId).future);
            },
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(
                  horizontal: 16, vertical: 12),
              itemCount: scenes.length,
              itemBuilder: (context, index) => _SceneCard(
                scene: scenes[index],
                isDark: isDark,
                onTap: () => _onSceneTap(context, scenes[index]),
              ),
            ),
          );
        },
      ),
    );
  }
}

/// Individual scene card widget.
class _SceneCard extends StatelessWidget {
  final Scene scene;
  final bool isDark;
  final VoidCallback onTap;

  const _SceneCard({
    required this.scene,
    required this.isDark,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLocked = !scene.isAvailable;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Material(
        borderRadius: BorderRadius.circular(16),
        color: isDark ? const Color(0xFF2A2A45) : Colors.white,
        elevation: isLocked ? 0 : 2,
        shadowColor: theme.colorScheme.primary.withOpacity(0.1),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: onTap,
          child: Opacity(
            opacity: isLocked ? 0.6 : 1.0,
            child: Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: isLocked
                      ? (isDark
                          ? const Color(0xFF3A3A55)
                          : const Color(0xFFE8E4DF))
                      : theme.colorScheme.primary.withOpacity(0.2),
                  width: 1,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // CG preview image (if available)
                  if (scene.sceneCgUrl != null &&
                      scene.sceneCgUrl!.isNotEmpty)
                    ClipRRect(
                      borderRadius: const BorderRadius.vertical(
                        top: Radius.circular(15),
                      ),
                      child: CachedNetworkImage(
                        imageUrl:
                            ApiClient.proxyImageUrl(scene.sceneCgUrl!),
                        height: 120,
                        width: double.infinity,
                        fit: BoxFit.cover,
                        placeholder: (_, __) => Container(
                          height: 120,
                          color: isDark
                              ? const Color(0xFF1A1A2E)
                              : const Color(0xFFF5F4F0),
                        ),
                        errorWidget: (_, __, ___) =>
                            const SizedBox.shrink(),
                      ),
                    ),

                  // Content
                  Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Title row with badges
                        Row(
                          children: [
                            // Lock icon
                            if (isLocked) ...[
                              Icon(
                                Icons.lock_outline,
                                size: 16,
                                color: theme.colorScheme.onSurface
                                    .withOpacity(0.5),
                              ),
                              const SizedBox(width: 6),
                            ],

                            // Scene name
                            Expanded(
                              child: Text(
                                scene.sceneName,
                                style:
                                    theme.textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w600,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),

                            // Scene type badge
                            _SceneTypeBadge(
                              label: scene.sceneTypeLabel,
                              sceneType: scene.sceneType,
                            ),
                          ],
                        ),

                        const SizedBox(height: 8),

                        // Description
                        Text(
                          scene.settingDescription,
                          style: theme.textTheme.bodySmall?.copyWith(
                            height: 1.4,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),

                        const SizedBox(height: 10),

                        // Bottom row: intimacy + cost
                        Row(
                          children: [
                            // Intimacy requirement
                            if (scene.requiredIntimacy > 0) ...[
                              Icon(
                                Icons.favorite_border,
                                size: 14,
                                color: theme.colorScheme.primary,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                '${scene.requiredIntimacy}',
                                style: theme.textTheme.labelSmall
                                    ?.copyWith(
                                  color: theme.colorScheme.primary,
                                ),
                              ),
                              const SizedBox(width: 12),
                            ],

                            // Max messages
                            Icon(
                              Icons.chat_bubble_outline,
                              size: 14,
                              color: theme.colorScheme.onSurface
                                  .withOpacity(0.5),
                            ),
                            const SizedBox(width: 4),
                            Text(
                              '${scene.maxMessages}条',
                              style: theme.textTheme.labelSmall,
                            ),

                            const Spacer(),

                            // Cost indicator
                            if (scene.isPaid) ...[
                              const Icon(
                                Icons.diamond_outlined,
                                size: 14,
                                color: Color(0xFFD4A84B),
                              ),
                              const SizedBox(width: 4),
                              Text(
                                '${scene.unlockCost}',
                                style: theme.textTheme.labelSmall
                                    ?.copyWith(
                                  color: const Color(0xFFD4A84B),
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ] else ...[
                              Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 8,
                                  vertical: 2,
                                ),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF5B8C6A)
                                      .withOpacity(0.12),
                                  borderRadius:
                                      BorderRadius.circular(8),
                                ),
                                child: Text(
                                  '免费',
                                  style: theme.textTheme.labelSmall
                                      ?.copyWith(
                                    color: const Color(0xFF5B8C6A),
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                            ],
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Scene type badge with color coding.
class _SceneTypeBadge extends StatelessWidget {
  final String label;
  final String sceneType;

  const _SceneTypeBadge({
    required this.label,
    required this.sceneType,
  });

  Color _getBadgeColor() {
    switch (sceneType) {
      case 'story':
        return const Color(0xFF6B4F8A);
      case 'date':
        return const Color(0xFFB76E79);
      case 'daily':
        return const Color(0xFF4A8A5E);
      case 'special':
        return const Color(0xFFD4A84B);
      default:
        return const Color(0xFF5A6872);
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = _getBadgeColor();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        label,
        style: GoogleFonts.inter(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}
