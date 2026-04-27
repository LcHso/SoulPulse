import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/providers/chat_provider.dart';
import '../../core/providers/notification_provider.dart';
import '../discover/discover_page.dart' show personasRefreshProvider;

class AppShell extends ConsumerStatefulWidget {
  final StatefulNavigationShell navigationShell;

  const AppShell({super.key, required this.navigationShell});

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  @override
  void initState() {
    super.initState();
    // Load unread counts on shell init
    Future.microtask(() {
      ref.read(notificationProvider.notifier).load();
    });
  }

  void _onDestinationSelected(int index) {
    widget.navigationShell.goBranch(
      index,
      initialLocation: index == widget.navigationShell.currentIndex,
    );
    // Refresh data on tab switch
    if (index == 1) {
      ref.read(personasRefreshProvider.notifier).state++;
    }
    if (index == 2) {
      ref.invalidate(unreadCountProvider);
      ref.invalidate(conversationsProvider);
    }
    if (index == 3) {
      ref.read(notificationProvider.notifier).load();
    }
  }

  @override
  Widget build(BuildContext context) {
    final unreadAsync = ref.watch(unreadCountProvider);
    final chatUnread = unreadAsync.valueOrNull ?? 0;
    final theme = Theme.of(context);

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth > 800) {
          // Desktop / tablet layout with NavigationRail
          return Scaffold(
            body: Row(
              children: [
                NavigationRail(
                  selectedIndex: widget.navigationShell.currentIndex,
                  onDestinationSelected: _onDestinationSelected,
                  labelType: NavigationRailLabelType.all,
                  backgroundColor: theme.colorScheme.surface,
                  indicatorColor: theme.colorScheme.primary.withValues(alpha: 0.15),
                  selectedIconTheme: IconThemeData(
                    color: theme.colorScheme.primary,
                  ),
                  selectedLabelTextStyle: TextStyle(
                    color: theme.colorScheme.primary,
                    fontWeight: FontWeight.w600,
                  ),
                  unselectedIconTheme: IconThemeData(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  unselectedLabelTextStyle: TextStyle(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  leading: const SizedBox(height: 16),
                  destinations: [
                    const NavigationRailDestination(
                      icon: Icon(Icons.home_outlined),
                      selectedIcon: Icon(Icons.home),
                      label: Text('Feed'),
                    ),
                    const NavigationRailDestination(
                      icon: Icon(Icons.explore_outlined),
                      selectedIcon: Icon(Icons.explore),
                      label: Text('Discover'),
                    ),
                    NavigationRailDestination(
                      icon: Badge(
                        isLabelVisible: chatUnread > 0,
                        label: Text('$chatUnread'),
                        child: const Icon(Icons.chat_bubble_outline),
                      ),
                      selectedIcon: Badge(
                        isLabelVisible: chatUnread > 0,
                        label: Text('$chatUnread'),
                        child: const Icon(Icons.chat_bubble),
                      ),
                      label: const Text('Chats'),
                    ),
                    const NavigationRailDestination(
                      icon: Icon(Icons.person_outline),
                      selectedIcon: Icon(Icons.person),
                      label: Text('Profile'),
                    ),
                  ],
                ),
                VerticalDivider(
                  thickness: 1,
                  width: 1,
                  color: theme.dividerTheme.color ??
                      (theme.brightness == Brightness.dark
                          ? const Color(0xFF3A3A55)
                          : const Color(0xFFE8E4DF)),
                ),
                Expanded(child: widget.navigationShell),
              ],
            ),
          );
        }

        // Mobile layout with bottom NavigationBar
        return Scaffold(
          body: widget.navigationShell,
          bottomNavigationBar: Container(
            decoration: BoxDecoration(
              border: Border(
                top: BorderSide(
                  color: theme.dividerTheme.color ??
                      (theme.brightness == Brightness.dark
                          ? const Color(0xFF3A3A55)
                          : const Color(0xFFE8E4DF)),
                  width: 1,
                ),
              ),
            ),
            child: NavigationBar(
              selectedIndex: widget.navigationShell.currentIndex,
              onDestinationSelected: _onDestinationSelected,
              destinations: [
                const NavigationDestination(
                  icon: Icon(Icons.home_outlined),
                  selectedIcon: Icon(Icons.home),
                  label: 'Feed',
                ),
                const NavigationDestination(
                  icon: Icon(Icons.explore_outlined),
                  selectedIcon: Icon(Icons.explore),
                  label: 'Discover',
                ),
                NavigationDestination(
                  icon: Badge(
                    isLabelVisible: chatUnread > 0,
                    label: Text('$chatUnread'),
                    child: const Icon(Icons.chat_bubble_outline),
                  ),
                  selectedIcon: Badge(
                    isLabelVisible: chatUnread > 0,
                    label: Text('$chatUnread'),
                    child: const Icon(Icons.chat_bubble),
                  ),
                  label: 'Chats',
                ),
                const NavigationDestination(
                  icon: Icon(Icons.person_outline),
                  selectedIcon: Icon(Icons.person),
                  label: 'Profile',
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
