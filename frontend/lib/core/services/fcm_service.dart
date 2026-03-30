/// Firebase Cloud Messaging Service for SoulPulse
///
/// STUB VERSION - Firebase dependencies commented out
/// This file provides a no-op implementation until Firebase is configured.
///
/// SETUP REQUIRED:
/// 1. Create Firebase project at https://console.firebase.google.com/
/// 2. Add Android app with package name: com.soulpulse.soulpulse
/// 3. Download google-services.json to: frontend/android/app/google-services.json
/// 4. Uncomment Firebase dependencies in pubspec.yaml
/// 5. Uncomment Firebase plugin in android/app/build.gradle
/// 6. Run: flutter pub get && flutter build apk
///
/// Once configured, replace this file with the full implementation.

class FcmService {
  static final FcmService _instance = FcmService._internal();
  factory FcmService() => _instance;
  FcmService._internal();

  String? _token;
  String? get token => _token;

  /// Initialize FCM. Returns immediately if Firebase not configured.
  Future<void> initialize() async {
    print('[FCM] Firebase not configured - using local notifications only');
    print('[FCM] To enable push notifications, follow setup instructions in fcm_service.dart');
    return;
  }

  /// Subscribe to a topic (no-op without Firebase)
  Future<void> subscribeToTopic(String topic) async {
    print('[FCM] subscribeToTopic: Firebase not configured');
  }

  /// Unsubscribe from a topic (no-op without Firebase)
  Future<void> unsubscribeFromTopic(String topic) async {
    print('[FCM] unsubscribeFromTopic: Firebase not configured');
  }

  /// Delete FCM token (no-op without Firebase)
  Future<void> deleteToken() async {
    _token = null;
    print('[FCM] deleteToken: Firebase not configured');
  }
}