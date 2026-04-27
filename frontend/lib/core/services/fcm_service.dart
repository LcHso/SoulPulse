// ============================================================================
// SoulPulse — Firebase Cloud Messaging Service
// ============================================================================
//
// STATUS: Code-ready stub (Firebase dependencies NOT yet active)
//
// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  3-STEP ACTIVATION GUIDE                                               ║
// ╠══════════════════════════════════════════════════════════════════════════╣
// ║                                                                        ║
// ║  Step 1: Create a Firebase project                                     ║
// ║    • Go to https://console.firebase.google.com/                        ║
// ║    • Create project → Add Android app (com.soulpulse.soulpulse)        ║
// ║    • Download google-services.json → android/app/google-services.json  ║
// ║                                                                        ║
// ║  Step 2: Uncomment dependencies in pubspec.yaml                        ║
// ║    • firebase_core: ^2.24.0                                            ║
// ║    • firebase_messaging: ^14.7.0                                       ║
// ║                                                                        ║
// ║  Step 3: Uncomment plugin in android/app/build.gradle                  ║
// ║    • id 'com.google.gms.google-services'                               ║
// ║                                                                        ║
// ║  Then run: flutter pub get && flutter build apk                        ║
// ║  After that, set _firebaseAvailable = true in this file.               ║
// ╚══════════════════════════════════════════════════════════════════════════╝
//
// Once Firebase is activated, uncomment the Firebase imports and method
// bodies marked with "// [FIREBASE]" below. Each section has the exact code
// you need to paste in.
//
// The `registerTokenWithBackend()` method works independently of Firebase —
// it simply POSTs the token to our backend. You can test it with any string.
//
// ============================================================================
library;

import 'dart:convert';
import 'package:http/http.dart' as http;
import '../api/api_client.dart';

// ─── [FIREBASE] Uncomment these imports when Firebase is enabled ─────────────
// import 'package:firebase_core/firebase_core.dart';
// import 'package:firebase_messaging/firebase_messaging.dart';
// ─────────────────────────────────────────────────────────────────────────────

/// Top-level background message handler.
///
/// [FIREBASE] When Firebase is enabled, uncomment and register this:
/// ```dart
/// @pragma('vm:entry-point')
/// Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
///   await Firebase.initializeApp();
///   print('[FCM] Background message: ${message.messageId}');
///   // Handle background message (e.g., show local notification)
/// }
/// ```
// @pragma('vm:entry-point')
// Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
//   await Firebase.initializeApp();
//   print('[FCM] Background message: ${message.messageId}');
// }

/// Callback type for incoming push notification messages.
typedef FcmMessageHandler = void Function(Map<String, dynamic> message);

/// Firebase Cloud Messaging service for SoulPulse.
///
/// Provides push notification capabilities with graceful degradation:
/// - When Firebase is NOT configured: all methods are safe no-ops.
/// - When Firebase IS configured: full push notification lifecycle management.
///
/// The service is a singleton — access via `FcmService()`.
class FcmService {
  // ── Singleton ────────────────────────────────────────────────────────────
  static final FcmService _instance = FcmService._internal();
  factory FcmService() => _instance;
  FcmService._internal();

  // ── Configuration ────────────────────────────────────────────────────────

  /// Set to `true` once Firebase dependencies are uncommented and configured.
  /// This flag gates all Firebase API calls to prevent runtime crashes.
  static const bool _firebaseAvailable = false;

  // ── State ────────────────────────────────────────────────────────────────

  /// The current FCM device token (null if Firebase is not active).
  String? _token;

  /// Public getter for the current FCM token.
  String? get token => _token;

  /// Whether initialization has completed successfully.
  bool _initialized = false;

  /// Whether the service has been initialized.
  bool get isInitialized => _initialized;

  /// Optional callback when a message is received while the app is in foreground.
  FcmMessageHandler? onMessageReceived;

  /// Optional callback when user taps a notification (app was in background).
  FcmMessageHandler? onNotificationTapped;

  // ── Initialization ───────────────────────────────────────────────────────

  /// Initialize the FCM service.
  ///
  /// When Firebase is available:
  /// 1. Initializes Firebase
  /// 2. Requests notification permission
  /// 3. Gets the device token
  /// 4. Registers token with backend
  /// 5. Sets up message handlers
  ///
  /// When Firebase is NOT available: logs a message and returns gracefully.
  Future<void> initialize() async {
    if (_initialized) return;

    if (!_firebaseAvailable) {
      print('[FCM] Firebase not configured — push notifications disabled');
      print('[FCM] To enable: follow 3-step guide in fcm_service.dart');
      _initialized = true;
      return;
    }

    // ─── [FIREBASE] Full initialization code ───────────────────────────────
    // try {
    //   await Firebase.initializeApp();
    //
    //   final messaging = FirebaseMessaging.instance;
    //
    //   // Request permission (iOS requires explicit request; Android auto-grants)
    //   final settings = await messaging.requestPermission(
    //     alert: true,
    //     badge: true,
    //     sound: true,
    //     provisional: false,
    //   );
    //   print('[FCM] Permission status: ${settings.authorizationStatus}');
    //
    //   if (settings.authorizationStatus == AuthorizationStatus.denied) {
    //     print('[FCM] Notifications denied by user');
    //     _initialized = true;
    //     return;
    //   }
    //
    //   // Get device token
    //   _token = await messaging.getToken();
    //   print('[FCM] Token obtained: ${_token?.substring(0, 20)}...');
    //
    //   // Register with backend
    //   if (_token != null) {
    //     await registerTokenWithBackend(_token!);
    //   }
    //
    //   // Listen for token refresh
    //   messaging.onTokenRefresh.listen((newToken) async {
    //     _token = newToken;
    //     await registerTokenWithBackend(newToken);
    //   });
    //
    //   // Set up foreground message handler
    //   FirebaseMessaging.onMessage.listen(_handleForegroundMessage);
    //
    //   // Set up background/terminated tap handler
    //   FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);
    //
    //   // Register background handler
    //   FirebaseMessaging.onBackgroundMessage(
    //     _firebaseMessagingBackgroundHandler,
    //   );
    //
    //   // Check if app was opened from a terminated-state notification
    //   final initialMessage = await messaging.getInitialMessage();
    //   if (initialMessage != null) {
    //     _handleNotificationTap(initialMessage);
    //   }
    //
    //   _initialized = true;
    //   print('[FCM] Initialization complete');
    // } catch (e) {
    //   print('[FCM] Initialization failed: $e');
    // }
    // ───────────────────────────────────────────────────────────────────────
  }

  // ── Backend Token Registration ───────────────────────────────────────────

  /// Register the FCM token with the SoulPulse backend.
  ///
  /// This method works independently of Firebase — it simply sends an HTTP
  /// request to store the device token for push targeting.
  ///
  /// [token] The FCM device token string.
  /// [platform] Device platform: "android", "ios", or "web".
  /// [deviceName] Optional human-readable device name.
  Future<bool> registerTokenWithBackend(
    String token, {
    String platform = 'android',
    String? deviceName,
  }) async {
    try {
      if (!ApiClient.isLoggedIn) {
        print('[FCM] Cannot register token: user not logged in');
        return false;
      }

      await ApiClient.post('/api/fcm/register', {
        'token': token,
        'platform': platform,
        if (deviceName != null) 'device_name': deviceName,
      });

      print('[FCM] Token registered with backend');
      return true;
    } catch (e) {
      print('[FCM] Failed to register token with backend: $e');
      return false;
    }
  }

  /// Unregister the current token from the backend (e.g., on logout).
  ///
  /// Call this when the user logs out to stop receiving push notifications
  /// on this device.
  Future<void> unregisterTokenFromBackend() async {
    if (_token == null) return;

    try {
      final uri = Uri.parse('${ApiClient.baseUrl}/api/fcm/unregister');
      await http
          .delete(
            uri,
            headers: {
              'Content-Type': 'application/json',
              if (ApiClient.token != null)
                'Authorization': 'Bearer ${ApiClient.token}',
            },
            body: jsonEncode({'token': _token}),
          )
          .timeout(const Duration(seconds: 10));
      print('[FCM] Token unregistered from backend');
    } catch (e) {
      print('[FCM] Failed to unregister token: $e');
    }
  }

  // ── Topic Subscription ───────────────────────────────────────────────────

  /// Subscribe to a notification topic (e.g., "new_posts", "announcements").
  ///
  /// [FIREBASE] When enabled, calls:
  /// `FirebaseMessaging.instance.subscribeToTopic(topic);`
  Future<void> subscribeToTopic(String topic) async {
    if (!_firebaseAvailable) {
      print('[FCM] subscribeToTopic("$topic"): Firebase not configured');
      return;
    }
    // [FIREBASE] Uncomment:
    // await FirebaseMessaging.instance.subscribeToTopic(topic);
    // print('[FCM] Subscribed to topic: $topic');
  }

  /// Unsubscribe from a notification topic.
  ///
  /// [FIREBASE] When enabled, calls:
  /// `FirebaseMessaging.instance.unsubscribeFromTopic(topic);`
  Future<void> unsubscribeFromTopic(String topic) async {
    if (!_firebaseAvailable) {
      print('[FCM] unsubscribeFromTopic("$topic"): Firebase not configured');
      return;
    }
    // [FIREBASE] Uncomment:
    // await FirebaseMessaging.instance.unsubscribeFromTopic(topic);
    // print('[FCM] Unsubscribed from topic: $topic');
  }

  // ── Token Management ─────────────────────────────────────────────────────

  /// Delete the FCM token from device and backend.
  ///
  /// Useful when the user explicitly opts out of notifications.
  Future<void> deleteToken() async {
    await unregisterTokenFromBackend();
    _token = null;

    if (!_firebaseAvailable) {
      print('[FCM] deleteToken: Firebase not configured');
      return;
    }
    // [FIREBASE] Uncomment:
    // await FirebaseMessaging.instance.deleteToken();
    // print('[FCM] Device token deleted');
  }

  // ── Message Handlers (internal) ──────────────────────────────────────────

  /// Handle a message received while the app is in the foreground.
  ///
  /// [FIREBASE] This is connected to FirebaseMessaging.onMessage stream.
  /// Parses the RemoteMessage and invokes [onMessageReceived] callback.
  // void _handleForegroundMessage(RemoteMessage message) {
  //   print('[FCM] Foreground message: ${message.notification?.title}');
  //   final data = <String, dynamic>{
  //     'title': message.notification?.title ?? '',
  //     'body': message.notification?.body ?? '',
  //     ...message.data,
  //   };
  //   onMessageReceived?.call(data);
  // }

  /// Handle notification tap when app was in background/terminated.
  ///
  /// [FIREBASE] This is connected to FirebaseMessaging.onMessageOpenedApp.
  /// Parses the RemoteMessage and invokes [onNotificationTapped] callback
  /// for navigation handling.
  // void _handleNotificationTap(RemoteMessage message) {
  //   print('[FCM] Notification tapped: ${message.data}');
  //   final data = <String, dynamic>{
  //     'title': message.notification?.title ?? '',
  //     'body': message.notification?.body ?? '',
  //     ...message.data,
  //   };
  //   onNotificationTapped?.call(data);
  // }
}
