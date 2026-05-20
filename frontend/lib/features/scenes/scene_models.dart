/// Scene data models for SoulPulse conversation scenes.
///
/// Contains:
/// - [Scene]: Represents an available scene for a persona
/// - [SceneContext]: Represents an active scene session state
/// - [SceneReward]: Represents rewards earned on scene completion

class Scene {
  final int id;
  final String sceneName;
  final String sceneType;
  final String settingDescription;
  final String? moodPreset;
  final int requiredIntimacy;
  final String unlockType;
  final int unlockCost;
  final int maxMessages;
  final String? sceneCgUrl;
  final bool isAvailable;
  final int? sortOrder;

  const Scene({
    required this.id,
    required this.sceneName,
    required this.sceneType,
    required this.settingDescription,
    this.moodPreset,
    required this.requiredIntimacy,
    required this.unlockType,
    required this.unlockCost,
    required this.maxMessages,
    this.sceneCgUrl,
    required this.isAvailable,
    this.sortOrder,
  });

  factory Scene.fromJson(Map<String, dynamic> json) {
    return Scene(
      id: json['id'] as int,
      sceneName: json['scene_name'] as String? ?? '',
      sceneType: json['scene_type'] as String? ?? 'story',
      settingDescription: json['setting_description'] as String? ?? '',
      moodPreset: json['mood_preset'] as String?,
      requiredIntimacy: json['required_intimacy'] as int? ?? 0,
      unlockType: json['unlock_type'] as String? ?? 'free',
      unlockCost: json['unlock_cost'] as int? ?? 0,
      maxMessages: json['max_messages'] as int? ?? 20,
      sceneCgUrl: json['scene_cg_url'] as String?,
      isAvailable: json['is_available'] as bool? ?? false,
      sortOrder: json['sort_order'] as int?,
    );
  }

  /// Whether this scene requires gems to unlock
  bool get isPaid => unlockType == 'gem' && unlockCost > 0;

  /// Whether this scene is locked due to intimacy requirements
  bool get isLockedByIntimacy => !isAvailable && requiredIntimacy > 0;

  /// Display label for scene type
  String get sceneTypeLabel {
    switch (sceneType) {
      case 'story':
        return '剧情';
      case 'date':
        return '约会';
      case 'daily':
        return '日常';
      case 'special':
        return '特别';
      default:
        return sceneType;
    }
  }
}

class SceneContext {
  final int sceneId;
  final String sceneName;
  final String systemPromptAddon;
  final String settingDescription;
  final int messagesRemaining;
  final String? moodPreset;
  final String? sceneCgUrl;
  final bool isCompleted;

  const SceneContext({
    required this.sceneId,
    required this.sceneName,
    required this.systemPromptAddon,
    required this.settingDescription,
    required this.messagesRemaining,
    this.moodPreset,
    this.sceneCgUrl,
    this.isCompleted = false,
  });

  factory SceneContext.fromJson(Map<String, dynamic> json) {
    return SceneContext(
      sceneId: json['scene_id'] as int? ?? 0,
      sceneName: json['scene_name'] as String? ?? '',
      systemPromptAddon: json['system_prompt_addon'] as String? ?? '',
      settingDescription: json['setting_description'] as String? ?? '',
      messagesRemaining: json['messages_remaining'] as int? ?? 0,
      moodPreset: json['mood_preset'] as String?,
      sceneCgUrl: json['scene_cg_url'] as String?,
      isCompleted: json['is_completed'] as bool? ?? false,
    );
  }
}

class SceneReward {
  final int intimacyBonus;
  final String? cgUnlockUrl;
  final String? cgTitle;
  final String? achievementBadge;

  const SceneReward({
    required this.intimacyBonus,
    this.cgUnlockUrl,
    this.cgTitle,
    this.achievementBadge,
  });

  factory SceneReward.fromJson(Map<String, dynamic> json) {
    return SceneReward(
      intimacyBonus: json['intimacy_bonus'] as int? ?? 0,
      cgUnlockUrl: json['cg_unlock_url'] as String?,
      cgTitle: json['cg_title'] as String?,
      achievementBadge: json['achievement_badge'] as String?,
    );
  }
}
