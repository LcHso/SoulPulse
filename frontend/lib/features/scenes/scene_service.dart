/// Scene service for SoulPulse.
///
/// Provides API integration for scene-related operations including
/// listing available scenes, starting/ending scenes, and making choices.

import '../../core/api/api_client.dart';
import 'scene_models.dart';

class SceneService {
  /// Get all available scenes for a persona.
  ///
  /// [personaId] The AI persona's ID
  /// Returns list of scenes (both available and locked)
  static Future<List<Scene>> getAvailableScenes(int personaId) async {
    try {
      final data = await ApiClient.getList(
        '/api/chat/scenes/$personaId',
        useCache: false,
      );
      return data
          .map((json) => Scene.fromJson(json as Map<String, dynamic>))
          .toList();
    } catch (e) {
      rethrow;
    }
  }

  /// Start a scene for a persona.
  ///
  /// [personaId] The AI persona's ID
  /// [sceneId] The scene to start
  /// Returns the active SceneContext
  static Future<SceneContext> startScene(int personaId, int sceneId) async {
    final data = await ApiClient.post(
      '/api/chat/scenes/$personaId/$sceneId/start',
      {},
    );
    return SceneContext.fromJson(data);
  }

  /// Get the currently active scene for a persona, if any.
  ///
  /// [personaId] The AI persona's ID
  /// Returns SceneContext if a scene is active, null otherwise
  static Future<SceneContext?> getActiveScene(int personaId) async {
    try {
      final data = await ApiClient.get(
        '/api/chat/scenes/$personaId/active',
        useCache: false,
      );
      if (data.isEmpty || data['scene_id'] == null) return null;
      return SceneContext.fromJson(data);
    } catch (_) {
      return null;
    }
  }

  /// End the currently active scene for a persona.
  ///
  /// [personaId] The AI persona's ID
  static Future<Map<String, dynamic>> endScene(int personaId) async {
    return await ApiClient.post(
      '/api/chat/scenes/$personaId/end',
      {},
    );
  }

  /// Submit a choice during an active scene.
  ///
  /// [personaId] The AI persona's ID
  /// [choiceKey] The choice identifier (e.g., 'CHOICE_A')
  static Future<Map<String, dynamic>> makeChoice(
    int personaId,
    String choiceKey,
  ) async {
    return await ApiClient.post(
      '/api/chat/scenes/$personaId/choice',
      {'choice_key': choiceKey},
    );
  }
}
