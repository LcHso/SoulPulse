import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:timeago/timeago.dart' as timeago;
import '../../core/providers/chat_provider.dart';

class ChatListPage extends ConsumerStatefulWidget {
  const ChatListPage({super.key});

  @override
  ConsumerState<ChatListPage> createState() => _ChatListPageState();
}

class _ChatListPageState extends ConsumerState<ChatListPage>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    Future.microtask(() => ref.read(conversationsProvider.notifier).refresh());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      ref.invalidate(conversationsProvider);
      ref.invalidate(unreadCountProvider);
    }
  }

  @override
  Widget build(BuildContext context) {
    final conversationsAsync = ref.watch(conversationsProvider);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: Text('Messages',
            style:
                GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 22)),
      ),
      body: conversationsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.chat_bubble_outline,
                  size: 48, color: Colors.grey[400]),
              const SizedBox(height: 12),
              Text('Failed to load conversations',
                  style: GoogleFonts.inter(color: Colors.grey)),
              TextButton(
                onPressed: () =>
                    ref.read(conversationsProvider.notifier).refresh(),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (conversations) {
          if (conversations.isEmpty) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.chat_bubble_outline,
                      size: 64, color: Colors.grey[300]),
                  const SizedBox(height: 16),
                  Text('No conversations yet',
                      style:
                          GoogleFonts.inter(fontSize: 16, color: Colors.grey)),
                  const SizedBox(height: 8),
                  Text('Start chatting with an AI from Discover!',
                      style: GoogleFonts.inter(
                          fontSize: 13, color: Colors.grey[500])),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: () => context.go('/discover'),
                    child: const Text('Discover AI'),
                  ),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: () => ref.read(conversationsProvider.notifier).refresh(),
            child: ListView.builder(
              itemCount: conversations.length,
              itemBuilder: (context, index) {
                final conv = conversations[index];
                final hasUnread = (conv['unread_count'] as int? ?? 0) > 0;
                final lastAt = conv['last_message_at'] as String? ?? '';

                String timeText = '';
                if (lastAt.isNotEmpty) {
                  try {
                    timeText = timeago.format(DateTime.parse(lastAt).toLocal());
                  } catch (_) {}
                }

                return ListTile(
                  leading: CircleAvatar(
                    radius: 28,
                    backgroundColor: Colors.grey[300],
                    backgroundImage:
                        (conv['ai_avatar'] as String?)?.isNotEmpty == true
                            ? CachedNetworkImageProvider(conv['ai_avatar'])
                            : null,
                    child: (conv['ai_avatar'] as String?)?.isNotEmpty != true
                        ? Text(
                            (conv['ai_name'] as String? ?? 'A')[0],
                            style: GoogleFonts.inter(
                                fontWeight: FontWeight.w600,
                                color: Colors.grey[700]),
                          )
                        : null,
                  ),
                  title: Row(
                    children: [
                      Expanded(
                        child: Text(
                          conv['ai_name'] ?? 'AI',
                          style: GoogleFonts.inter(
                            fontWeight:
                                hasUnread ? FontWeight.w700 : FontWeight.w500,
                            fontSize: 15,
                          ),
                        ),
                      ),
                      Text(
                        timeText,
                        style: GoogleFonts.inter(
                          fontSize: 12,
                          color: hasUnread
                              ? const Color(0xFF0095F6)
                              : Colors.grey[500],
                        ),
                      ),
                    ],
                  ),
                  subtitle: Row(
                    children: [
                      Expanded(
                        child: Text(
                          conv['last_message'] ?? '',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: GoogleFonts.inter(
                            fontSize: 13,
                            color: hasUnread
                                ? (isDark ? Colors.white70 : Colors.black87)
                                : Colors.grey[500],
                            fontWeight:
                                hasUnread ? FontWeight.w500 : FontWeight.normal,
                          ),
                        ),
                      ),
                      if (hasUnread)
                        Container(
                          margin: const EdgeInsets.only(left: 8),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: const Color(0xFF0095F6),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Text(
                            '${conv['unread_count']}',
                            style: GoogleFonts.inter(
                                fontSize: 11,
                                color: Colors.white,
                                fontWeight: FontWeight.w600),
                          ),
                        ),
                    ],
                  ),
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                  onTap: () async {
                    final aiId = conv['ai_id'] as int;
                    final aiName = conv['ai_name'] as String? ?? 'AI';
                    await context.push(
                        '/chat/$aiId?name=${Uri.encodeComponent(aiName)}');
                    // Refresh conversations when returning from chat
                    if (mounted) {
                      ref.read(conversationsProvider.notifier).refresh();
                      ref.invalidate(unreadCountProvider);
                    }
                  },
                );
              },
            ),
          );
        },
      ),
    );
  }
}
