import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// Navigation menu widget for persona-related features.
///
/// Displayed on persona profile/detail pages to provide access to:
/// - CG Gallery
/// - Outfits (wardrobe)
/// - Streak / Interaction history
/// - Subscription management
class PersonaFeaturesMenu extends StatelessWidget {
  final int personaId;
  final String personaName;

  const PersonaFeaturesMenu({
    super.key,
    required this.personaId,
    required this.personaName,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF2A2A45) : Colors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(isDark ? 0.2 : 0.05),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        children: [
          _FeatureTile(
            icon: Icons.collections_outlined,
            iconColor: Colors.pink.shade300,
            title: 'CG相册',
            subtitle: '解锁专属插画',
            onTap: () => context.push(
              '/gallery/$personaId?name=${Uri.encodeComponent(personaName)}',
            ),
          ),
          _divider(isDark),
          _FeatureTile(
            icon: Icons.checkroom_outlined,
            iconColor: Colors.teal.shade400,
            title: '衣柜',
            subtitle: '更换TA的穿搭',
            onTap: () => context.push(
              '/outfits/$personaId?name=${Uri.encodeComponent(personaName)}',
            ),
          ),
          _divider(isDark),
          _FeatureTile(
            icon: Icons.local_fire_department_outlined,
            iconColor: Colors.orange.shade400,
            title: '互动记录',
            subtitle: '连续打卡 & 每日仪式',
            onTap: () => context.push(
              '/streak/$personaId?name=${Uri.encodeComponent(personaName)}',
            ),
          ),
          _divider(isDark),
          _FeatureTile(
            icon: Icons.workspace_premium_outlined,
            iconColor: Colors.amber.shade600,
            title: '订阅',
            subtitle: '解锁更多功能',
            onTap: () => context.push('/subscription'),
          ),
          _divider(isDark),
          _FeatureTile(
            icon: Icons.auto_awesome_outlined,
            iconColor: Colors.purple.shade300,
            title: '导入角色卡',
            subtitle: 'SillyTavern PNG / JSON',
            onTap: () => context.push('/import-character'),
          ),
        ],
      ),
    );
  }

  Widget _divider(bool isDark) {
    return Divider(
      height: 1,
      indent: 56,
      color: isDark ? Colors.white10 : Colors.grey.shade100,
    );
  }
}

/// Individual feature list tile with icon, title, and subtitle
class _FeatureTile extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _FeatureTile({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: iconColor.withOpacity(0.12),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, color: iconColor, size: 20),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  Text(
                    subtitle,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              Icons.chevron_right,
              size: 20,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ],
        ),
      ),
    );
  }
}
