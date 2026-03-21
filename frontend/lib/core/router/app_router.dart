import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/auth_provider.dart';
import '../../features/shell/app_shell.dart';
import '../../features/auth/login_page.dart';
import '../../features/auth/onboarding_page.dart';
import '../../features/feed/feed_page.dart';
import '../../features/discover/discover_page.dart';
import '../../features/chat/chat_list_page.dart';
import '../../features/chat/chat_page.dart';
import '../../features/profile/user_profile_page.dart';
import '../../features/profile/settings_page.dart';
import '../../features/profile/ai_profile_page.dart';
import '../../features/profile/post_detail_page.dart';
import '../../features/feed/story_player_page.dart';
import '../../features/legal/legal_pages.dart';
import '../../features/notifications/notification_page.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();
final shellNavigatorKey = GlobalKey<NavigatorState>();

final routerProvider = Provider<GoRouter>((ref) {
  final loggedIn = ref.watch(isLoggedInProvider);

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: '/feed',
    redirect: (context, state) {
      final isLoginRoute = state.matchedLocation == '/login';
      final isOnboarding = state.matchedLocation == '/onboarding';

      if (!loggedIn && !isLoginRoute && !isOnboarding) return '/login';
      if (loggedIn && isLoginRoute) return '/feed';
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginPage(),
      ),
      GoRoute(
        path: '/onboarding',
        builder: (context, state) => const OnboardingPage(),
      ),
      // Main shell with bottom navigation
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) {
          return AppShell(navigationShell: navigationShell);
        },
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/feed',
                builder: (context, state) => const FeedPage(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/discover',
                builder: (context, state) => const DiscoverPage(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/chats',
                builder: (context, state) => const ChatListPage(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/profile',
                builder: (context, state) => const UserProfilePage(),
              ),
            ],
          ),
        ],
      ),
      // Full-screen routes (outside shell)
      GoRoute(
        path: '/chat/:aiId',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) {
          final aiId = int.parse(state.pathParameters['aiId']!);
          final aiName = state.uri.queryParameters['name'] ?? 'AI';
          final postContext = state.uri.queryParameters['context'];
          return ChatPage(aiId: aiId, aiName: aiName, postContext: postContext);
        },
      ),
      GoRoute(
        path: '/ai/:aiId',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) {
          final aiId = int.parse(state.pathParameters['aiId']!);
          final aiName = state.uri.queryParameters['name'] ?? 'AI';
          return AIProfilePage(aiId: aiId, aiName: aiName);
        },
      ),
      GoRoute(
        path: '/post-detail',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) {
          final extra = state.extra as Map<String, dynamic>;
          return PostDetailPage(
            post: extra['post'] as Map<String, dynamic>,
            aiName: extra['aiName'] as String,
            aiAvatar: extra['aiAvatar'] as String,
          );
        },
      ),
      GoRoute(
        path: '/story',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) {
          final extra = state.extra as Map<String, dynamic>;
          return StoryPlayerPage(
            stories: extra['stories'] as List<dynamic>,
            aiName: extra['aiName'] as String,
            aiId: extra['aiId'] as int,
          );
        },
      ),
      GoRoute(
        path: '/settings',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) => const SettingsPage(),
      ),
      GoRoute(
        path: '/notifications',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) => const NotificationPage(),
      ),
      GoRoute(
        path: '/privacy',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) => const PrivacyPolicyPage(),
      ),
      GoRoute(
        path: '/terms',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) => const TermsOfServicePage(),
      ),
    ],
  );
});
