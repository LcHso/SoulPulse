import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:timeago/timeago.dart' as timeago;
import '../../core/providers/notification_provider.dart';
import '../../core/services/local_notification_service.dart';

class NotificationPage extends ConsumerStatefulWidget {
  const NotificationPage({super.key});

  @override
  ConsumerState<NotificationPage> createState() => _NotificationPageState();
}

class _NotificationPageState extends ConsumerState<NotificationPage> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() async {
      await ref.read(notificationProvider.notifier).load();
      // Reset poll baseline so already-seen notifications
      // don't re-trigger system notifications
      if (!kIsWeb) {
        final state = ref.read(notificationProvider);
        LocalNotificationService.resetUnreadBaseline(state.unreadCount);
      }
    });
  }

  /// Navigate to the source of the notification
  void _onNotificationTap(Map<String, dynamic> notif) {
    final isRead = notif['is_read'] == true;
    // Mark as read
    if (!isRead) {
      final id = notif['id'] as int?;
      if (id != null) {
        ref.read(notificationProvider.notifier).markOneRead(id);
      }
    }

    // Parse data_json for navigation
    final type = notif['type'] as String? ?? '';
    Map<String, dynamic>? data;
    try {
      final json = notif['data_json'] as String?;
      if (json != null && json.isNotEmpty) {
        data = jsonDecode(json) as Map<String, dynamic>;
      }
    } catch (_) {}

    switch (type) {
      case 'comment_reply':
      case 'new_post':
        // Navigate to post detail
        if (data != null && data['post_id'] != null) {
          final aiId = data['ai_id'] as int? ?? 1;
          final postId = data['post_id'] as int?;
          // Fetch post and navigate
          _navigateToPost(postId!, aiId);
        }
        break;
      case 'proactive_dm':
        // Navigate to chat
        if (data != null && data['ai_id'] != null) {
          final aiId = data['ai_id'] as int;
          final aiName = data['ai_name'] as String? ?? 'AI';
          context.push('/chat/$aiId?name=${Uri.encodeComponent(aiName)}');
        }
        break;
      case 'intimacy_upgrade':
        // Navigate to AI profile
        if (data != null && data['ai_id'] != null) {
          final aiId = data['ai_id'] as int;
          final aiName = data['ai_name'] as String? ?? 'AI';
          context.push('/ai/$aiId?name=${Uri.encodeComponent(aiName)}');
        }
        break;
    }
  }

  Future<void> _navigateToPost(int postId, int aiId) async {
    try {
      final posts =
          await ref.read(notificationProvider.notifier).fetchPost(postId);
      if (posts != null && mounted) {
        context.push('/post-detail', extra: {
          'post': posts,
          'aiName': posts['ai_name'] ?? 'AI',
          'aiAvatar': posts['ai_avatar'] ?? '',
        });
      }
    } catch (_) {
      // Fallback: navigate to AI profile
      if (mounted) {
        context.push('/ai/$aiId?name=AI');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(notificationProvider);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: Text('Notifications',
            style:
                GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 18)),
        actions: [
          if (state.unreadCount > 0)
            TextButton(
              onPressed: () =>
                  ref.read(notificationProvider.notifier).markAllRead(),
              child: const Text('Mark all read'),
            ),
        ],
      ),
      body: state.isLoading && state.notifications.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : state.notifications.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.notifications_none,
                          size: 64, color: Colors.grey[300]),
                      const SizedBox(height: 16),
                      Text('No notifications yet',
                          style: GoogleFonts.inter(
                              fontSize: 16, color: Colors.grey)),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: () =>
                      ref.read(notificationProvider.notifier).load(),
                  child: ListView.builder(
                    itemCount: state.notifications.length,
                    itemBuilder: (context, index) {
                      final notif = state.notifications[index];
                      final isRead = notif['is_read'] == true;
                      String timeText = '';
                      try {
                        timeText = timeago.format(
                            DateTime.parse(notif['created_at'] ?? '')
                                .toLocal());
                      } catch (_) {}

                      return Container(
                        color: isRead
                            ? null
                            : (isDark
                                ? Colors.blue.withAlpha(15)
                                : Colors.blue.withAlpha(8)),
                        child: ListTile(
                          leading: CircleAvatar(
                            radius: 20,
                            backgroundColor:
                                _typeColor(notif['type'] ?? '').withAlpha(30),
                            child: Icon(_typeIcon(notif['type'] ?? ''),
                                size: 20,
                                color: _typeColor(notif['type'] ?? '')),
                          ),
                          title: Text(
                            notif['title'] ?? '',
                            style: GoogleFonts.inter(
                              fontWeight:
                                  isRead ? FontWeight.normal : FontWeight.w600,
                              fontSize: 14,
                            ),
                          ),
                          subtitle: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              if ((notif['body'] as String?)?.isNotEmpty ==
                                  true)
                                Text(notif['body'],
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: GoogleFonts.inter(
                                        fontSize: 12, color: Colors.grey[500])),
                              Text(timeText,
                                  style: GoogleFonts.inter(
                                      fontSize: 11, color: Colors.grey[400])),
                            ],
                          ),
                          trailing: !isRead
                              ? Container(
                                  width: 8,
                                  height: 8,
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF0095F6),
                                    shape: BoxShape.circle,
                                  ),
                                )
                              : const Icon(Icons.chevron_right,
                                  size: 18, color: Colors.grey),
                          contentPadding: const EdgeInsets.symmetric(
                              horizontal: 16, vertical: 4),
                          onTap: () => _onNotificationTap(notif),
                        ),
                      );
                    },
                  ),
                ),
    );
  }

  IconData _typeIcon(String type) {
    switch (type) {
      case 'comment_reply':
        return Icons.chat_bubble;
      case 'proactive_dm':
        return Icons.favorite;
      case 'intimacy_upgrade':
        return Icons.trending_up;
      case 'new_post':
        return Icons.photo;
      default:
        return Icons.notifications;
    }
  }

  Color _typeColor(String type) {
    switch (type) {
      case 'comment_reply':
        return const Color(0xFF0095F6);
      case 'proactive_dm':
        return Colors.pink;
      case 'intimacy_upgrade':
        return Colors.purple;
      case 'new_post':
        return Colors.green;
      default:
        return Colors.grey;
    }
  }
}
