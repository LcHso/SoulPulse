import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:timeago/timeago.dart' as timeago;
import '../../core/providers/chat_provider.dart';
import '../../core/api/api_client.dart';
import '../../core/theme/character_theme.dart';
import '../../core/widgets/empty_state.dart';

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
            return EmptyState(
              icon: Icons.chat_bubble_outline,
              title: 'No conversations yet',
              subtitle: 'Discover AI companions to start chatting',
              actionLabel: 'Explore',
              onAction: () => context.go('/discover'),
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

                final characterColors =
                    CharacterTheme.getPalette(conv['ai_name'] as String?);

                return Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                  child: Material(
                    color: Theme.of(context).colorScheme.surface,
                    borderRadius: BorderRadius.circular(16),
                    elevation: 0,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(16),
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
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 12),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(16),
                          border: Border(
                            left: BorderSide(
                              color: characterColors.primary
                                  .withValues(alpha: hasUnread ? 0.6 : 0.25),
                              width: 3,
                            ),
                          ),
                        ),
                        child: Row(
                          children: [
                            CircleAvatar(
                              radius: 26,
                              backgroundColor: Colors.grey[300],
                              backgroundImage:
                                  (conv['ai_avatar'] as String?)?.isNotEmpty ==
                                          true
                                      ? CachedNetworkImageProvider(
                                          ApiClient.proxyImageUrl(
                                              conv['ai_avatar'] as String))
                                      : null,
                              child: (conv['ai_avatar'] as String?)
                                          ?.isNotEmpty !=
                                      true
                                  ? Text(
                                      (conv['ai_name'] as String? ?? 'A')[0],
                                      style: GoogleFonts.inter(
                                          fontWeight: FontWeight.w600,
                                          color: Colors.grey[700]),
                                    )
                                  : null,
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Text(
                                          conv['ai_name'] ?? 'AI',
                                          style: GoogleFonts.inter(
                                            fontWeight: FontWeight.w600,
                                            fontSize: 16,
                                          ),
                                        ),
                                      ),
                                      Text(
                                        timeText,
                                        style: Theme.of(context)
                                            .textTheme
                                            .labelSmall,
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 4),
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Text(
                                          conv['last_message'] ?? '',
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall,
                                        ),
                                      ),
                                      if (hasUnread)
                                        Container(
                                          margin:
                                              const EdgeInsets.only(left: 8),
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 6, vertical: 2),
                                          decoration: BoxDecoration(
                                            color: Theme.of(context)
                                                .colorScheme
                                                .primary,
                                            borderRadius:
                                                BorderRadius.circular(10),
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
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}
