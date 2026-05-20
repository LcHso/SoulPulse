/// Outfit data models

class Outfit {
  final int id;
  final int personaId;
  final String outfitName;
  final String category; // daily, formal, workout, intimate, event
  final String? thumbnailUrl;
  final Map<String, dynamic> unlockCondition;
  final bool isDefault;
  final bool isAvailable; // unlocked for this user
  final bool isEquipped;

  const Outfit({
    required this.id,
    required this.personaId,
    required this.outfitName,
    required this.category,
    this.thumbnailUrl,
    required this.unlockCondition,
    required this.isDefault,
    required this.isAvailable,
    this.isEquipped = false,
  });

  factory Outfit.fromJson(Map<String, dynamic> json) {
    return Outfit(
      id: json['id'] as int,
      personaId: json['persona_id'] as int,
      outfitName: json['outfit_name'] as String? ?? '',
      category: json['category'] as String? ?? 'daily',
      thumbnailUrl: json['thumbnail_url'] as String?,
      unlockCondition:
          (json['unlock_condition'] as Map<String, dynamic>?) ?? {},
      isDefault: json['is_default'] as bool? ?? false,
      isAvailable: json['is_available'] as bool? ?? false,
      isEquipped: json['is_equipped'] as bool? ?? false,
    );
  }

  /// Display-friendly category label
  String get categoryLabel {
    switch (category) {
      case 'daily':
        return '日常';
      case 'formal':
        return '正装';
      case 'workout':
        return '运动';
      case 'intimate':
        return '私密';
      case 'event':
        return '活动';
      default:
        return category;
    }
  }
}
