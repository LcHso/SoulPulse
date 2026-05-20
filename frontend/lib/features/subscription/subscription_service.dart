import '../../core/api/api_client.dart';

/// Subscription tier info
class SubscriptionTier {
  final int id;
  final String name;
  final String displayName;
  final int priceGems; // monthly cost in gems
  final List<String> benefits;
  final bool isCurrent;

  const SubscriptionTier({
    required this.id,
    required this.name,
    required this.displayName,
    required this.priceGems,
    required this.benefits,
    this.isCurrent = false,
  });

  factory SubscriptionTier.fromJson(Map<String, dynamic> json) {
    return SubscriptionTier(
      id: json['id'] as int,
      name: json['name'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '',
      priceGems: json['price_gems'] as int? ?? 0,
      benefits: (json['benefits'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      isCurrent: json['is_current'] as bool? ?? false,
    );
  }
}

/// Active subscription status
class SubscriptionStatus {
  final String tierName;
  final String? expiryDate;
  final bool autoRenew;

  const SubscriptionStatus({
    required this.tierName,
    this.expiryDate,
    required this.autoRenew,
  });

  factory SubscriptionStatus.fromJson(Map<String, dynamic> json) {
    return SubscriptionStatus(
      tierName: json['tier_name'] as String? ?? 'free',
      expiryDate: json['expiry_date'] as String?,
      autoRenew: json['auto_renew'] as bool? ?? false,
    );
  }
}

/// Service for subscription management
class SubscriptionService {
  /// Get available subscription tiers
  Future<List<SubscriptionTier>> getTiers() async {
    try {
      final data = await ApiClient.getList(
        '/api/subscription/tiers',
        useCache: true,
      );
      return data
          .map((item) =>
              SubscriptionTier.fromJson(item as Map<String, dynamic>))
          .toList();
    } catch (_) {
      // Return placeholder tiers if API not ready
      return _placeholderTiers;
    }
  }

  /// Get current user subscription status
  Future<SubscriptionStatus> getMySubscription() async {
    try {
      final data = await ApiClient.get(
        '/api/subscription/my-subscription',
        useCache: false,
      );
      return SubscriptionStatus.fromJson(data);
    } catch (_) {
      return const SubscriptionStatus(tierName: 'free', autoRenew: false);
    }
  }

  /// Subscribe to a tier
  Future<bool> subscribe(int tierId) async {
    try {
      await ApiClient.post('/api/subscription/subscribe/$tierId', {});
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Cancel auto-renew
  Future<bool> cancelAutoRenew() async {
    try {
      await ApiClient.post('/api/subscription/cancel', {});
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Placeholder tiers for UI development
  static const _placeholderTiers = [
    SubscriptionTier(
      id: 1,
      name: 'free',
      displayName: '基础版',
      priceGems: 0,
      benefits: ['每日20条消息', '基础情绪系统', '1个AI伙伴'],
    ),
    SubscriptionTier(
      id: 2,
      name: 'vip',
      displayName: 'VIP',
      priceGems: 300,
      benefits: [
        '每日100条消息',
        '高级情绪系统',
        '3个AI伙伴',
        'CG相册解锁加速',
        '专属衣装',
        '优先回复',
      ],
    ),
    SubscriptionTier(
      id: 3,
      name: 'svip',
      displayName: 'SVIP',
      priceGems: 800,
      benefits: [
        '无限消息',
        '完整情绪系统 + 特殊剧情',
        '全部AI伙伴',
        '全CG解锁',
        '全部衣装',
        '优先回复 + 语音消息',
        '专属称号',
        '生日惊喜',
      ],
    ),
  ];
}
