import '../../core/api/api_client.dart';
import 'gallery_models.dart';

/// Service for CG Gallery operations
class GalleryService {
  /// Fetch all CG illustrations for a persona
  ///
  /// Returns a list of CGs with their unlock/collection status
  /// for the currently authenticated user.
  Future<List<CGIllustration>> getCGsForPersona(int personaId) async {
    try {
      final data = await ApiClient.getList(
        '/api/ai/$personaId/cg-gallery',
        useCache: false,
      );
      return data
          .map((item) =>
              CGIllustration.fromJson(item as Map<String, dynamic>))
          .toList();
    } catch (_) {
      // API may not exist yet — return empty list
      return [];
    }
  }

  /// Mark a CG as viewed by the user
  Future<void> markAsViewed(int cgId) async {
    try {
      await ApiClient.post('/api/cg/$cgId/view', {});
    } catch (_) {
      // Silently fail if endpoint doesn't exist
    }
  }
}
