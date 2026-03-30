import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import '../api/api_client.dart';

/// Callback for handling notification taps (must be top-level or static).
@pragma('vm:entry-point')
void onDidReceiveNotificationResponse(NotificationResponse response) {
  // Store the payload for the app to handle when it's ready
  LocalNotificationService.pendingPayload = response.payload;
  LocalNotificationService.onTapController.add(response.payload ?? '');
}

class LocalNotificationService {
  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  static Timer? _pollTimer;
  static int _lastKnownUnread = 0;
  static bool _initialized = false;

  /// Stream that emits notification payload when user taps a notification.
  /// Public for FCM service to emit events.
  static final StreamController<String> onTapController =
      StreamController<String>.broadcast();
  static Stream<String> get onNotificationTap => onTapController.stream;

  /// Pending payload from notification tap (public for FCM service).
  static String? pendingPayload;

  /// Get and clear any pending payload from a notification tap that
  /// launched or resumed the app.
  static String? consumePendingPayload() {
    final p = pendingPayload;
    pendingPayload = null;
    return p;
  }

  /// Initialize the notification plugin. Call once from main().
  static Future<void> init() async {
    if (_initialized || kIsWeb) return;

    const androidSettings =
        AndroidInitializationSettings('@mipmap/ic_launcher');

    const initSettings = InitializationSettings(android: androidSettings);

    await _plugin.initialize(
      initSettings,
      onDidReceiveNotificationResponse: onDidReceiveNotificationResponse,
    );

    // Request notification permission on Android 13+
    final androidImpl = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    if (androidImpl != null) {
      await androidImpl.requestNotificationsPermission();
    }

    _initialized = true;
  }

  /// Start periodic polling for new notifications.
  static void startPolling({Duration interval = const Duration(seconds: 30)}) {
    if (kIsWeb) return;
    stopPolling();
    // Initial check after 5 seconds
    Future.delayed(const Duration(seconds: 5), _checkForNew);
    _pollTimer = Timer.periodic(interval, (_) => _checkForNew());
  }

  /// Stop polling.
  static void stopPolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
  }

  static Future<void> _checkForNew() async {
    if (!ApiClient.isLoggedIn) return;

    try {
      final data = await ApiClient.get('/api/notifications/unread-count',
          useCache: false);
      final unread = (data['unread_count'] as int?) ?? 0;

      if (unread > _lastKnownUnread && _lastKnownUnread >= 0) {
        // There are new notifications — fetch the latest ones
        final listData =
            await ApiClient.get('/api/notifications', useCache: false);
        final notifs = (listData['notifications'] as List<dynamic>?) ?? [];

        // Show system notification for each new unread item
        int shown = 0;
        for (final n in notifs) {
          if (n['is_read'] == true) continue;
          if (shown >= (unread - _lastKnownUnread)) break;

          await _showNotification(n as Map<String, dynamic>);
          shown++;
        }
      }

      _lastKnownUnread = unread;
    } catch (_) {
      // Silently ignore polling errors
    }
  }

  static Future<void> _showNotification(Map<String, dynamic> notif) async {
    final id = (notif['id'] as int?) ?? DateTime.now().millisecondsSinceEpoch;
    final title = notif['title'] as String? ?? 'SoulPulse';
    final body = notif['body'] as String? ?? '';
    final type = notif['type'] as String? ?? '';

    // Build payload for navigation on tap
    final payload = jsonEncode({
      'id': id,
      'type': type,
      'data_json': notif['data_json'],
    });

    String channelId = 'soulpulse_default';
    String channelName = 'SoulPulse';
    String channelDesc = 'SoulPulse notifications';

    // Use different channels for different notification types
    if (type == 'proactive_dm') {
      channelId = 'soulpulse_messages';
      channelName = 'Messages';
      channelDesc = 'Chat messages from AI companions';
    } else if (type == 'comment_reply') {
      channelId = 'soulpulse_comments';
      channelName = 'Comments';
      channelDesc = 'Replies to your comments';
    } else if (type == 'new_post') {
      channelId = 'soulpulse_posts';
      channelName = 'New Posts';
      channelDesc = 'New posts from AI companions you follow';
    }

    final androidDetails = AndroidNotificationDetails(
      channelId,
      channelName,
      channelDescription: channelDesc,
      importance: Importance.high,
      priority: Priority.high,
      showWhen: true,
      enableVibration: true,
      icon: '@mipmap/ic_launcher',
    );

    await _plugin.show(
      id % 100000, // keep ID manageable
      title,
      body,
      NotificationDetails(android: androidDetails),
      payload: payload,
    );
  }

  /// Reset the known unread count (e.g. when user views notifications).
  static void resetUnreadBaseline(int current) {
    _lastKnownUnread = current;
  }

  static void dispose() {
    stopPolling();
  }
}
