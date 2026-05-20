/// Scene completion celebration dialog for SoulPulse.
///
/// Full-screen overlay shown when a scene completes, displaying:
/// - "场景完成!" title with sparkle animation
/// - Rewards: intimacy bonus, CG unlock thumbnail, achievement badge
/// - Confetti/sparkle particle animation
/// - "Continue" button to return to normal chat

import 'dart:math';
import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/api/api_client.dart';
import 'scene_models.dart';

/// Full-screen celebration overlay for scene completion.
class SceneCompletionDialog extends StatefulWidget {
  final String sceneName;
  final SceneReward? reward;
  final VoidCallback onContinue;

  const SceneCompletionDialog({
    super.key,
    required this.sceneName,
    this.reward,
    required this.onContinue,
  });

  /// Show as a full-screen overlay.
  static Future<void> show(
    BuildContext context, {
    required String sceneName,
    SceneReward? reward,
    required VoidCallback onContinue,
  }) {
    return showGeneralDialog(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.black.withOpacity(0.7),
      transitionDuration: const Duration(milliseconds: 400),
      pageBuilder: (_, __, ___) => SceneCompletionDialog(
        sceneName: sceneName,
        reward: reward,
        onContinue: onContinue,
      ),
      transitionBuilder: (context, animation, secondaryAnimation, child) {
        return FadeTransition(
          opacity: CurvedAnimation(parent: animation, curve: Curves.easeOut),
          child: ScaleTransition(
            scale: Tween<double>(begin: 0.85, end: 1.0).animate(
              CurvedAnimation(parent: animation, curve: Curves.elasticOut),
            ),
            child: child,
          ),
        );
      },
    );
  }

  @override
  State<SceneCompletionDialog> createState() => _SceneCompletionDialogState();
}

class _SceneCompletionDialogState extends State<SceneCompletionDialog>
    with TickerProviderStateMixin {
  late AnimationController _sparkleCtrl;
  late AnimationController _fadeInCtrl;
  late Animation<double> _fadeIn;
  final List<_Particle> _particles = [];
  final _random = Random();

  @override
  void initState() {
    super.initState();

    // Sparkle loop animation
    _sparkleCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat();

    // Content fade-in
    _fadeInCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _fadeIn = CurvedAnimation(parent: _fadeInCtrl, curve: Curves.easeOut);
    _fadeInCtrl.forward();

    // Generate sparkle particles
    for (int i = 0; i < 20; i++) {
      _particles.add(_Particle(
        x: _random.nextDouble(),
        y: _random.nextDouble(),
        size: _random.nextDouble() * 6 + 2,
        speed: _random.nextDouble() * 0.5 + 0.3,
        delay: _random.nextDouble(),
      ));
    }
  }

  @override
  void dispose() {
    _sparkleCtrl.dispose();
    _fadeInCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Material(
      color: Colors.transparent,
      child: Stack(
        children: [
          // Sparkle particles
          AnimatedBuilder(
            animation: _sparkleCtrl,
            builder: (context, _) => CustomPaint(
              size: MediaQuery.of(context).size,
              painter: _SparklesPainter(
                particles: _particles,
                progress: _sparkleCtrl.value,
                color: theme.colorScheme.primary,
              ),
            ),
          ),

          // Main content
          Center(
            child: FadeTransition(
              opacity: _fadeIn,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 32),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Title
                    Text(
                      '场景完成!',
                      style: GoogleFonts.playfairDisplay(
                        fontSize: 32,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      widget.sceneName,
                      style: GoogleFonts.inter(
                        fontSize: 16,
                        color: Colors.white.withOpacity(0.8),
                      ),
                      textAlign: TextAlign.center,
                    ),

                    const SizedBox(height: 32),

                    // Rewards card
                    if (widget.reward != null) _buildRewardsCard(theme, isDark),

                    const SizedBox(height: 32),

                    // Continue button
                    SizedBox(
                      width: 200,
                      height: 48,
                      child: ElevatedButton(
                        onPressed: () {
                          Navigator.of(context).pop();
                          widget.onContinue();
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: theme.colorScheme.primary,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(24),
                          ),
                          elevation: 4,
                        ),
                        child: Text(
                          '继续',
                          style: GoogleFonts.inter(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRewardsCard(ThemeData theme, bool isDark) {
    final reward = widget.reward!;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: (isDark ? const Color(0xFF22223A) : Colors.white)
            .withOpacity(0.95),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: theme.colorScheme.primary.withOpacity(0.2),
            blurRadius: 20,
            spreadRadius: 2,
          ),
        ],
      ),
      child: Column(
        children: [
          Text(
            '获得奖励',
            style: GoogleFonts.inter(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: theme.colorScheme.onSurface.withOpacity(0.6),
            ),
          ),
          const SizedBox(height: 14),

          // Intimacy bonus
          if (reward.intimacyBonus > 0)
            _RewardRow(
              icon: Icons.favorite,
              iconColor: theme.colorScheme.primary,
              label: '亲密度',
              value: '+${reward.intimacyBonus}',
            ),

          // CG unlock
          if (reward.cgUnlockUrl != null) ...[
            const SizedBox(height: 12),
            _RewardRow(
              icon: Icons.image,
              iconColor: const Color(0xFF6B4F8A),
              label: reward.cgTitle ?? 'CG解锁',
              value: '已解锁',
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: CachedNetworkImage(
                imageUrl: ApiClient.proxyImageUrl(reward.cgUnlockUrl!),
                height: 100,
                width: double.infinity,
                fit: BoxFit.cover,
                placeholder: (_, __) => Container(
                  height: 100,
                  color: isDark
                      ? const Color(0xFF1A1A2E)
                      : const Color(0xFFF5F4F0),
                ),
                errorWidget: (_, __, ___) => const SizedBox.shrink(),
              ),
            ),
          ],

          // Achievement badge
          if (reward.achievementBadge != null) ...[
            const SizedBox(height: 12),
            _RewardRow(
              icon: Icons.emoji_events,
              iconColor: const Color(0xFFD4A84B),
              label: reward.achievementBadge!,
              value: '达成',
            ),
          ],
        ],
      ),
    );
  }
}

/// Individual reward row display.
class _RewardRow extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String label;
  final String value;

  const _RewardRow({
    required this.icon,
    required this.iconColor,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      children: [
        Container(
          width: 32,
          height: 32,
          decoration: BoxDecoration(
            color: iconColor.withOpacity(0.12),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(icon, size: 18, color: iconColor),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            label,
            style: theme.textTheme.bodyMedium,
          ),
        ),
        Text(
          value,
          style: GoogleFonts.inter(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: iconColor,
          ),
        ),
      ],
    );
  }
}

/// Particle data for sparkle animation.
class _Particle {
  final double x;
  final double y;
  final double size;
  final double speed;
  final double delay;

  const _Particle({
    required this.x,
    required this.y,
    required this.size,
    required this.speed,
    required this.delay,
  });
}

/// Custom painter for sparkle/confetti particles.
class _SparklesPainter extends CustomPainter {
  final List<_Particle> particles;
  final double progress;
  final Color color;

  _SparklesPainter({
    required this.particles,
    required this.progress,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    for (final p in particles) {
      final animProgress = ((progress + p.delay) % 1.0);
      final opacity = (1.0 - animProgress) * 0.8;
      if (opacity <= 0) continue;

      final paint = Paint()
        ..color = color.withOpacity(opacity.clamp(0.0, 1.0))
        ..style = PaintingStyle.fill;

      final x = p.x * size.width;
      final y = p.y * size.height - (animProgress * p.speed * size.height * 0.3);

      canvas.drawCircle(Offset(x, y), p.size * (1 - animProgress * 0.5), paint);
    }
  }

  @override
  bool shouldRepaint(covariant _SparklesPainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}
