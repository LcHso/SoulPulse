// Web implementation using dart:html
// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;

class WebNotificationService {
  static bool _permissionGranted = false;

  static Future<void> requestPermission() async {
    try {
      final result = await html.Notification.requestPermission();
      _permissionGranted = result == 'granted';
    } catch (_) {
      _permissionGranted = false;
    }
  }

  static bool get isPermissionGranted => _permissionGranted;

  static void showNotification(String title, String body) {
    if (!_permissionGranted) return;
    try {
      html.Notification(title, body: body, icon: '/icons/Icon-192.png');
    } catch (_) {}
  }
}
