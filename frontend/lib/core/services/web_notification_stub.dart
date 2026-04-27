// Stub for non-web platforms
class WebNotificationService {
  static Future<void> requestPermission() async {}
  static bool get isPermissionGranted => false;
  static void showNotification(String title, String body) {}
}
