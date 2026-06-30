import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/providers/chat_provider.dart';
import '../../core/providers/notification_provider.dart';
import '../../core/theme/breakpoints.dart';
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
    if (index == 4) {
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
        final tier = Breakpoints.getTier(constraints.maxWidth);

        switch (tier) {
          case LayoutTier.desktop:
            return _buildDesktopLayout(theme, chatUnread);
          case LayoutTier.tablet:
            return _buildTabletLayout(theme, chatUnread);
          case LayoutTier.mobile:
            return _buildMobileLayout(theme, chatUnread);
        }
      },
    );
  }

  // ─── Desktop: Full sidebar with labels ────────────────────────────────

  Widget _buildDesktopLayout(ThemeData theme, int chatUnread) {
    final currentIndex = widget.navigationShell.currentIndex;

    return Scaffold(
      body: Row(
        children: [
          // Extended sidebar navigation
          Container(
            width: 220,
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              border: Border(
                right: BorderSide(
                  color: theme.dividerTheme.color ??
                      (theme.brightness == Brightness.dark
                          ? const Color(0xFF3A3A55)
                          : const Color(0xFFE8E4DF)),
                  width: 1,
                ),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Brand header
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
                  child: Text(
                    'SoulPulse',
                    style: GoogleFonts.playfairDisplay(
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.primary,
                    ),
                  ),
                ),
                // Navigation items
                _buildSidebarItem(
                  icon: Icons.home_outlined,
                  selectedIcon: Icons.home,
                  label: 'Feed',
                  index: 0,
                  isSelected: currentIndex == 0,
                  theme: theme,
                ),
                _buildSidebarItem(
                  icon: Icons.explore_outlined,
                  selectedIcon: Icons.explore,
                  label: 'Discover',
                  index: 1,
                  isSelected: currentIndex == 1,
                  theme: theme,
                ),
                _buildSidebarItem(
                  icon: Icons.chat_bubble_outline,
                  selectedIcon: Icons.chat_bubble,
                  label: 'Chats',
                  index: 2,
                  isSelected: currentIndex == 2,
                  theme: theme,
                  badge: chatUnread,
                ),
                _buildSidebarItem(
                  icon: Icons.people_alt_outlined,
                  selectedIcon: Icons.people_alt,
                  label: '我的角色',
                  index: 3,
                  isSelected: currentIndex == 3,
                  theme: theme,
                ),
                _buildSidebarItem(
                  icon: Icons.person_outline,
                  selectedIcon: Icons.person,
                  label: 'Profile',
                  index: 4,
                  isSelected: currentIndex == 4,
                  theme: theme,
                ),
              ],
            ),
          ),
          // Main content area
          Expanded(child: widget.navigationShell),
        ],
      ),
    );
  }

  Widget _buildSidebarItem({
    required IconData icon,
    required IconData selectedIcon,
    required String label,
    required int index,
    required bool isSelected,
    required ThemeData theme,
    int badge = 0,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      child: Material(
        color: isSelected
            ? theme.colorScheme.primary.withValues(alpha: 0.1)
            : Colors.transparent,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => _onDestinationSelected(index),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(
              children: [
                Icon(
                  isSelected ? selectedIcon : icon,
                  size: 22,
                  color: isSelected
                      ? theme.colorScheme.primary
                      : theme.colorScheme.onSurfaceVariant,
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(
                    label,
                    style: GoogleFonts.inter(
                      fontSize: 14,
                      fontWeight:
                          isSelected ? FontWeight.w600 : FontWeight.w400,
                      color: isSelected
                          ? theme.colorScheme.primary
                          : theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
                if (badge > 0)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      badge > 99 ? '99+' : '$badge',
                      style: GoogleFonts.inter(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: theme.colorScheme.onPrimary,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // ─── Tablet: NavigationRail ────────────────────────────────────────────

  Widget _buildTabletLayout(ThemeData theme, int chatUnread) {
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
                icon: Icon(Icons.people_alt_outlined),
                selectedIcon: Icon(Icons.people_alt),
                label: Text('我的角色'),
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

  // ─── Mobile: Bottom NavigationBar ──────────────────────────────────────

  Widget _buildMobileLayout(ThemeData theme, int chatUnread) {
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
              icon: Icon(Icons.people_alt_outlined),
              selectedIcon: Icon(Icons.people_alt),
              label: '我的角色',
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
  }
}
