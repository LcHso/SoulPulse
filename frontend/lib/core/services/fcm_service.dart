/// Firebase Cloud Messaging Service for SoulPulse
///
/// Handles push notifications in all app states:
/// - Foreground: Shows notification while app is visible
/// - Background: Shows notification when app is minimized
/// - Terminated: Shows notification when app is killed
///
/// SETUP REQUIRED:
/// 1. Create Firebase project at https://console.firebase.google.com/
/// 2. Add Android app with package name: com.soulpulse.soulpulse
/// 3. Download google-services.json and replace the placeholder in:
///    frontend/android/app/google-services.json
/// 4. Run: flutter pub get
/// 5. Rebuild the app

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'dart:convert';

import 'local_notification_service.dart';

/// Background message handler (must be top-level function)
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  // Initialize Firebase for background isolate
  await Firebase.initializeApp();

  print('[FCM] Background message received: ${message.messageId}');

  // Show local notification for background messages
  await _showLocalNotification(message);
}

Future<void> _showLocalNotification(RemoteMessage message) async {
  final notification = message.notification;
  final data = message.data;

  if (notification == null) return;

  final flutterLocalNotificationsPlugin = FlutterLocalNotificationsPlugin();

  // Initialize for background
  const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
  const initSettings = InitializationSettings(android: androidSettings);
  await flutterLocalNotificationsPlugin.initialize(initSettings);

  // Show notification
  await flutterLocalNotificationsPlugin.show(
    notification.hashCode,
    notification.title,
    notification.body,
    NotificationDetails(
      android: AndroidNotificationDetails(
        'soulpulse_fcm',
        'SoulPulse Notifications',
        channelDescription: 'Push notifications from SoulPulse',
        importance: Importance.high,
        priority: Priority.high,
        icon: '@mipmap/ic_launcher',
      ),
    ),
    payload: data.isNotEmpty ? jsonEncode(data) : null,
  );
}

class FcmService {
  static final FcmService _instance = FcmService._internal();
  factory FcmService() => _instance;
  FcmService._internal();

  final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  String? _token;
  String? get token => _token;

  /// Initialize FCM. Call this in main() before runApp()
  Future<void> initialize() async {
    try {
      // Check if google-services.json is configured
      // This will throw if Firebase is not properly configured
      await Firebase.initializeApp();
      print('[FCM] Firebase initialized successfully');
    } catch (e) {
      print('[FCM] Firebase initialization failed: $e');
      print('[FCM] Ensure google-services.json is properly configured.');
      print('[FCM] Falling back to local notifications only.');
      return;
    }

    // Request permission (required for iOS, optional for Android)
    final settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      provisional: false,
    );

    print('[FCM] Permission status: ${settings.authorizationStatus}');

    // Get FCM token
    _token = await _messaging.getToken();
    print('[FCM] Token: $_token');

    // Listen for token refresh
    _messaging.onTokenRefresh.listen((token) {
      _token = token;
      print('[FCM] Token refreshed: $token');
      // TODO: Send token to backend for storage
      _sendTokenToBackend(token);
    });

    // Register background message handler
    FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

    // Handle foreground messages
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      print('[FCM] Foreground message: ${message.messageId}');
      _handleForegroundMessage(message);
    });

    // Handle message when app is opened from background
    FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
      print('[FCM] Message opened app: ${message.messageId}');
      _handleMessageTap(message);
    });

    // Check if app was opened from a notification when terminated
    final initialMessage = await _messaging.getInitialMessage();
    if (initialMessage != null) {
      print('[FCM] Initial message: ${initialMessage.messageId}');
      _handleMessageTap(initialMessage);
    }
  }

  /// Handle messages received while app is in foreground
  void _handleForegroundMessage(RemoteMessage message) {
    final notification = message.notification;
    final data = message.data;

    if (notification != null) {
      // Show local notification
      _showLocalNotification(message);
    }

    // Handle data payload
    if (data.isNotEmpty) {
      print('[FCM] Data payload: $data');
    }
  }

  /// Handle notification tap
  void _handleMessageTap(RemoteMessage message) {
    final data = message.data;

    // Navigate based on notification type
    final type = data['type'];
    final aiId = data['ai_id'];
    final postId = data['post_id'];

    print('[FCM] Tapped notification: type=$type, aiId=$aiId, postId=$postId');

    // Navigation will be handled by the app's router
    // Store the data for the router to process
    LocalNotificationService().handleNotificationTap(
      type: type,
      aiId: aiId != null ? int.tryParse(aiId) : null,
      postId: postId != null ? int.tryParse(postId) : null,
    );
  }

  /// Send FCM token to backend for storage
  Future<void> _sendTokenToBackend(String token) async {
    // TODO: Implement API call to store token
    // POST /api/users/fcm-token with { "token": token }
    print('[FCM] Token ready to send to backend: $token');
  }

  /// Subscribe to a topic (e.g., for broadcast notifications)
  Future<void> subscribeToTopic(String topic) async {
    try {
      await _messaging.subscribeToTopic(topic);
      print('[FCM] Subscribed to topic: $topic');
    } catch (e) {
      print('[FCM] Failed to subscribe to topic: $e');
    }
  }

  /// Unsubscribe from a topic
  Future<void> unsubscribeFromTopic(String topic) async {
    try {
      await _messaging.unsubscribeFromTopic(topic);
      print('[FCM] Unsubscribed from topic: $topic');
    } catch (e) {
      print('[FCM] Failed to unsubscribe from topic: $e');
    }
  }

  /// Delete FCM token (e.g., on logout)
  Future<void> deleteToken() async {
    try {
      await _messaging.deleteToken();
      _token = null;
      print('[FCM] Token deleted');
    } catch (e) {
      print('[FCM] Failed to delete token: $e');
    }
  }
}