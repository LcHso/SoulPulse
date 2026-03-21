import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/api_client.dart';

/// Notification list + unread count.
class NotificationState {
  final List<Map<String, dynamic>> notifications;
  final int unreadCount;
  final bool isLoading;

  const NotificationState({
    this.notifications = const [],
    this.unreadCount = 0,
    this.isLoading = false,
  });
}

class NotificationNotifier extends Notifier<NotificationState> {
  @override
  NotificationState build() {
    return const NotificationState();
  }

  Future<void> load() async {
    state = NotificationState(
      notifications: state.notifications,
      unreadCount: state.unreadCount,
      isLoading: true,
    );
    try {
      final data = await ApiClient.get('/api/notifications', useCache: false);
      final notifs =
          (data['notifications'] as List<dynamic>).cast<Map<String, dynamic>>();
      final unread = (data['unread_count'] as int?) ?? 0;
      state = NotificationState(
        notifications: notifs,
        unreadCount: unread,
      );
    } catch (_) {
      state = NotificationState(
        notifications: state.notifications,
        unreadCount: state.unreadCount,
      );
    }
  }

  Future<void> markAllRead() async {
    try {
      await ApiClient.post('/api/notifications/mark-read', {});
      final updated = state.notifications.map((n) {
        return {...n, 'is_read': true};
      }).toList();
      state = NotificationState(notifications: updated, unreadCount: 0);
    } catch (_) {}
  }

  Future<void> markOneRead(int notificationId) async {
    try {
      await ApiClient.post('/api/notifications/$notificationId/read', {});
      final updated = state.notifications.map((n) {
        if (n['id'] == notificationId) {
          return {...n, 'is_read': true};
        }
        return n;
      }).toList();
      final newUnread = (state.unreadCount - 1).clamp(0, state.unreadCount);
      state = NotificationState(
        notifications: updated,
        unreadCount: newUnread,
      );
    } catch (_) {}
  }

  /// Fetch a single post by ID for navigation from notification
  Future<Map<String, dynamic>?> fetchPost(int postId) async {
    try {
      final data =
          await ApiClient.get('/api/feed/posts/$postId', useCache: false);
      return data;
    } catch (_) {
      return null;
    }
  }
}

final notificationProvider =
    NotifierProvider<NotificationNotifier, NotificationState>(
        NotificationNotifier.new);
