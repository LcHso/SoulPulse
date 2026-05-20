/// CG Gallery data models

class CGIllustration {
  final int id;
  final int personaId;
  final String title;
  final String? description;
  final String imageUrl;
  final String? thumbnailUrl;
  final String qualityTier; // standard, premium, limited
  final Map<String, dynamic> unlockCondition;
  final bool isCollected;

  const CGIllustration({
    required this.id,
    required this.personaId,
    required this.title,
    this.description,
    required this.imageUrl,
    this.thumbnailUrl,
    required this.qualityTier,
    required this.unlockCondition,
    required this.isCollected,
  });

  factory CGIllustration.fromJson(Map<String, dynamic> json) {
    return CGIllustration(
      id: json['id'] as int,
      personaId: json['persona_id'] as int,
      title: json['title'] as String? ?? '',
      description: json['description'] as String?,
      imageUrl: json['image_url'] as String? ?? '',
      thumbnailUrl: json['thumbnail_url'] as String?,
      qualityTier: json['quality_tier'] as String? ?? 'standard',
      unlockCondition:
          (json['unlock_condition'] as Map<String, dynamic>?) ?? {},
      isCollected: json['is_collected'] as bool? ?? false,
    );
  }

  /// Display text for the quality tier badge
  String get qualityLabel {
    switch (qualityTier) {
      case 'premium':
        return 'SSR';
      case 'limited':
        return '限定';
      default:
        return 'SR';
    }
  }
}
