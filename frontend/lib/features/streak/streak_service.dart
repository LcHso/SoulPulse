import '../../core/api/api_client.dart';
import 'streak_models.dart';

/// Service for streak and ritual configuration
class StreakService {
  /// Get streak info for the user's interaction with a persona
  Future<StreakInfo> getStreakInfo(int personaId) async {
    try {
      final data = await ApiClient.get(
        '/api/chat/$personaId/streak',
        useCache: false,
      );
      return StreakInfo.fromJson(data);
    } catch (_) {
      // Return default info if endpoint not ready
      return const StreakInfo(
        currentStreak: 0,
        totalDays: 0,
        nextMilestone: 7,
        nextMilestoneReward: {},
      );
    }
  }

  /// Get current ritual configuration
  Future<RitualConfig> getRitualConfig(int personaId) async {
    try {
      final data = await ApiClient.get(
        '/api/chat/$personaId/rituals',
        useCache: false,
      );
      return RitualConfig.fromJson(data);
    } catch (_) {
      return RitualConfig();
    }
  }

  /// Save ritual configuration
  Future<bool> configureRituals(int personaId, RitualConfig config) async {
    try {
      await ApiClient.post(
        '/api/chat/$personaId/configure-rituals',
        config.toJson(),
      );
      return true;
    } catch (_) {
      return false;
    }
  }
}
