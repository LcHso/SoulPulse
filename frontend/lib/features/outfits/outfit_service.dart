import '../../core/api/api_client.dart';
import 'outfit_models.dart';

/// Service for outfit operations
class OutfitService {
  /// Fetch available outfits for a persona (for the current user)
  Future<List<Outfit>> getOutfitsForPersona(int personaId) async {
    try {
      final data = await ApiClient.getList(
        '/api/ai/$personaId/outfits',
        useCache: false,
      );
      return data
          .map((item) => Outfit.fromJson(item as Map<String, dynamic>))
          .toList();
    } catch (_) {
      // API may not exist yet — return empty list
      return [];
    }
  }

  /// Equip an outfit for a persona
  Future<bool> equipOutfit(int personaId, int outfitId) async {
    try {
      await ApiClient.post('/api/ai/$personaId/outfits/$outfitId/equip', {});
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Attempt to unlock an outfit (gem purchase)
  Future<bool> unlockOutfit(int personaId, int outfitId) async {
    try {
      await ApiClient.post('/api/ai/$personaId/outfits/$outfitId/unlock', {});
      return true;
    } catch (_) {
      return false;
    }
  }
}
