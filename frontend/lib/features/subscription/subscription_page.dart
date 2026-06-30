import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'subscription_service.dart';

// ─── Providers ────────────────────────────────────────────────────────────────

/// Combined subscription data: tiers + current status
class SubscriptionData {
  final List<SubscriptionTier> tiers;
  final SubscriptionStatus status;

  const SubscriptionData({required this.tiers, required this.status});
}

final subscriptionDataProvider = FutureProvider<SubscriptionData>((ref) async {
  final service = SubscriptionService();
  final tiers = await service.getTiers();
  final status = await service.getMySubscription();
  return SubscriptionData(tiers: tiers, status: status);
});

// ─── Page ─────────────────────────────────────────────────────────────────────

/// Subscription management page.
///
/// Features:
/// - Current tier badge at top
/// - Tier comparison cards: Free vs VIP vs SVIP
/// - Benefits list per tier with checkmarks
/// - Price display (gems/month)
/// - Subscribe button (with confirmation dialog)
/// - Active subscription info: expiry, auto-renew toggle
class SubscriptionPage extends ConsumerStatefulWidget {
  const SubscriptionPage({super.key});

  @override
  ConsumerState<SubscriptionPage> createState() => _SubscriptionPageState();
}

class _SubscriptionPageState extends ConsumerState<SubscriptionPage> {
  final SubscriptionService _service = SubscriptionService();
  int? _subscribingTierId;

  Future<void> _subscribe(SubscriptionTier tier) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('订阅 ${tier.displayName}'),
        content: Text(
          tier.priceGems > 0
              ? '确定使用 ${tier.priceGems} 星钻/月 订阅${tier.displayName}吗？'
              : '确定切换到基础版吗？',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('确认'),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    setState(() => _subscribingTierId = tier.id);
    final success = await _service.subscribe(tier.id);
    if (mounted) {
      setState(() => _subscribingTierId = null);
      if (success) {
        HapticFeedback.heavyImpact();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已订阅 ${tier.displayName}')),
        );
        ref.invalidate(subscriptionDataProvider);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('订阅失败，请稍后重试')),
        );
      }
    }
  }

  Future<void> _toggleAutoRenew(SubscriptionStatus status) async {
    if (!status.autoRenew) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('取消自动续费'),
        content: const Text('确定取消自动续费吗？订阅将在到期后失效。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('保留'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('确认取消'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      final success = await _service.cancelAutoRenew();
      if (success) {
        ref.invalidate(subscriptionDataProvider);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final asyncData = ref.watch(subscriptionDataProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('订阅管理'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, size: 20),
          onPressed: () => context.pop(),
        ),
      ),
      body: asyncData.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline,
                  size: 48, color: theme.colorScheme.error),
              const SizedBox(height: 12),
              Text('加载失败', style: theme.textTheme.bodyMedium),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: () => ref.invalidate(subscriptionDataProvider),
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('重试'),
              ),
            ],
          ),
        ),
        data: (data) => SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              // Current tier badge
              _buildCurrentTier(data.status, theme, isDark),
              const SizedBox(height: 20),
              // Tier cards
              ...data.tiers.map((tier) => Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: _buildTierCard(tier, data.status, theme, isDark),
                  )),
              // Subscription info
              if (data.status.tierName != 'free') ...[
                const SizedBox(height: 8),
                _buildSubscriptionInfo(data.status, theme, isDark),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCurrentTier(
      SubscriptionStatus status, ThemeData theme, bool isDark) {
    final tierName = status.tierName;
    final (label, color, icon) = _tierVisuals(tierName);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [color.withOpacity(0.2), color.withOpacity(0.05)],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: color, size: 28),
          ),
          const SizedBox(width: 14),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '当前等级',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              Text(
                label,
                style: theme.textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildTierCard(SubscriptionTier tier, SubscriptionStatus status,
      ThemeData theme, bool isDark) {
    final isCurrent = status.tierName == tier.name;
    final (_, color, icon) = _tierVisuals(tier.name);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF2A2A45) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: isCurrent ? Border.all(color: color, width: 2) : null,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(isDark ? 0.2 : 0.06),
            blurRadius: 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            children: [
              Icon(icon, color: color, size: 22),
              const SizedBox(width: 8),
              Text(
                tier.displayName,
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
              ),
              const Spacer(),
              if (isCurrent)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    '当前',
                    style: TextStyle(
                        color: color,
                        fontSize: 11,
                        fontWeight: FontWeight.bold),
                  ),
                )
              else if (tier.priceGems > 0)
                Text(
                  '${tier.priceGems} 星钻/月',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          // Benefits
          ...tier.benefits.map((benefit) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.check_circle, size: 16, color: color),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        benefit,
                        style: theme.textTheme.bodySmall,
                      ),
                    ),
                  ],
                ),
              )),
          // Subscribe button (if not current)
          if (!isCurrent && tier.priceGems > 0) ...[
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              height: 40,
              child: FilledButton(
                onPressed: _subscribingTierId == tier.id
                    ? null
                    : () => _subscribe(tier),
                style: FilledButton.styleFrom(
                  backgroundColor: color,
                ),
                child: _subscribingTierId == tier.id
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white),
                      )
                    : const Text('立即订阅'),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildSubscriptionInfo(
      SubscriptionStatus status, ThemeData theme, bool isDark) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF2A2A45) : Colors.white,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('订阅信息',
              style: theme.textTheme.titleSmall
                  ?.copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(height: 10),
          if (status.expiryDate != null)
            _infoRow('到期日期', status.expiryDate!, theme),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('自动续费', style: theme.textTheme.bodyMedium),
              Switch.adaptive(
                value: status.autoRenew,
                onChanged:
                    status.autoRenew ? (_) => _toggleAutoRenew(status) : null,
                activeColor: theme.colorScheme.primary,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _infoRow(String label, String value, ThemeData theme) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: theme.textTheme.bodyMedium),
        Text(value,
            style: theme.textTheme.bodyMedium
                ?.copyWith(fontWeight: FontWeight.w500)),
      ],
    );
  }

  (String, Color, IconData) _tierVisuals(String tierName) {
    switch (tierName) {
      case 'vip':
        return ('VIP', Colors.amber.shade700, Icons.workspace_premium);
      case 'svip':
        return ('SVIP', Colors.purple.shade400, Icons.diamond_outlined);
      default:
        return ('基础版', Colors.blueGrey, Icons.person_outline);
    }
  }
}
