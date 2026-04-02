// ============================================================================
// SoulPulse 应用路由配置
// ============================================================================
//
// 本文件使用 GoRouter 配置应用的导航系统，包含：
// - 路由定义与页面映射
// - 登录状态路由守卫（未登录重定向到登录页）
// - 底部导航栏的 Shell 路由结构
// - 全屏页面的独立路由
// - 管理员页面的权限控制
//
// 路由结构：
// - /login: 登录页面
// - /onboarding: 新用户引导页面
// - /feed, /discover, /chats, /profile: Shell 内的底部导航页面
// - /chat/:aiId: 全屏聊天页面
// - /ai/:aiId: AI 详情页面
// - /post-detail: 帖子详情页面
// - /story: 故事播放器页面
// - /settings, /notifications: 设置和通知页面
// - /admin, /admin/pending: 管理员后台页面（需要管理员权限）
//
// ============================================================================

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
import '../../features/admin/admin_shell.dart';

/// 根导航器的 GlobalKey
///
/// 用于全屏路由的导航，确保它们覆盖底部导航栏
final _rootNavigatorKey = GlobalKey<NavigatorState>();

/// Shell 导航器的 GlobalKey
///
/// 用于底部导航栏内的路由导航
final shellNavigatorKey = GlobalKey<NavigatorState>();

/// 路由 Provider
///
/// 使用 Riverpod 创建 GoRouter 实例，
/// 监听登录状态变化以实现路由守卫
final routerProvider = Provider<GoRouter>((ref) {
  // 监听登录状态派生 Provider，避免用户数据刷新时触发重定向
  final loggedIn = ref.watch(isLoggedInProvider);

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: '/feed', // 应用启动时的初始路由

    /// 全局重定向回调
    ///
    /// 实现登录状态路由守卫：
    /// - 未登录用户访问非登录/引导页面时重定向到登录页
    /// - 已登录用户访问登录页时重定向到信息流页面
    redirect: (context, state) {
      final isLoginRoute = state.matchedLocation == '/login';
      final isOnboarding = state.matchedLocation == '/onboarding';

      // 未登录且不在登录/引导页面，重定向到登录页
      if (!loggedIn && !isLoginRoute && !isOnboarding) return '/login';

      // 已登录但在登录页面，重定向到信息流页面
      if (loggedIn && isLoginRoute) return '/feed';

      // 其他情况不重定向
      return null;
    },

    /// 路由配置列表
    routes: [
      // ================== 登录与引导页面 ==================
      /// 登录页面路由
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginPage(),
      ),

      /// 新用户引导页面路由
      GoRoute(
        path: '/onboarding',
        builder: (context, state) => const OnboardingPage(),
      ),

      // ================== 主 Shell 路由（底部导航） ==================
      /// StatefulShellRoute 提供底部导航栏的页面结构
      ///
      /// 使用 indexedStack 保持各页面状态
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) {
          // AppShell 包含底部导航栏和页面容器
          return AppShell(navigationShell: navigationShell);
        },
        branches: [
          // 信息流页面分支（底部导航第一项）
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/feed',
                builder: (context, state) => const FeedPage(),
              ),
            ],
          ),

          // 发现页面分支（底部导航第二项）
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/discover',
                builder: (context, state) => const DiscoverPage(),
              ),
            ],
          ),

          // 聊天列表页面分支（底部导航第三项）
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/chats',
                builder: (context, state) => const ChatListPage(),
              ),
            ],
          ),

          // 用户个人页面分支（底部导航第四项）
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

      // ================== 全屏路由（覆盖底部导航） ==================

      /// 聊天页面路由
      ///
      /// 使用 parentNavigatorKey 确保全屏显示
      ///
      /// 路径参数：
      /// - aiId: AI 的 ID
      ///
      /// 查询参数：
      /// - name: AI 名称
      /// - context: 帖子上下文（可选）
      GoRoute(
        path: '/chat/:aiId',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) {
          // 解析路径参数
          final aiId = int.parse(state.pathParameters['aiId']!);

          // 解析查询参数
          final aiName = state.uri.queryParameters['name'] ?? 'AI';
          final postContext = state.uri.queryParameters['context'];

          return ChatPage(aiId: aiId, aiName: aiName, postContext: postContext);
        },
      ),

      /// AI 详情页面路由
      ///
      /// 显示 AI 人设的详细信息、情绪状态等
      ///
      /// 路径参数：
      /// - aiId: AI 的 ID
      ///
      /// 查询参数：
      /// - name: AI 名称
      GoRoute(
        path: '/ai/:aiId',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) {
          final aiId = int.parse(state.pathParameters['aiId']!);
          final aiName = state.uri.queryParameters['name'] ?? 'AI';

          return AIProfilePage(aiId: aiId, aiName: aiName);
        },
      ),

      /// 帖子详情页面路由
      ///
      /// 通过 extra 参数传递帖子数据
      GoRoute(
        path: '/post-detail',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) {
          // 从 extra 参数获取帖子数据
          final extra = state.extra as Map<String, dynamic>;

          return PostDetailPage(
            post: extra['post'] as Map<String, dynamic>,
            aiName: extra['aiName'] as String,
            aiAvatar: extra['aiAvatar'] as String,
          );
        },
      ),

      /// 故事播放器页面路由
      ///
      /// 用于播放 AI 发布的故事内容
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

      /// 设置页面路由
      GoRoute(
        path: '/settings',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) => const SettingsPage(),
      ),

      /// 通知页面路由
      GoRoute(
        path: '/notifications',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) => const NotificationPage(),
      ),

      // ================== 法律条款页面 ==================

      /// 隐私政策页面路由
      GoRoute(
        path: '/privacy',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) => const PrivacyPolicyPage(),
      ),

      /// 服务条款页面路由
      GoRoute(
        path: '/terms',
        parentNavigatorKey: _rootNavigatorKey,
        builder: (context, state) => const TermsOfServicePage(),
      ),

      // ================== 管理员后台路由 ==================

      /// 管理员后台首页路由
      ///
      /// 包含权限重定向：非管理员用户重定向到信息流页面
      GoRoute(
        path: '/admin',
        parentNavigatorKey: _rootNavigatorKey,
        redirect: (context, state) {
          // 检查管理员权限
          final isAdmin = ref.read(isAdminProvider);
          if (!isAdmin) return '/feed';
          return null;
        },
        builder: (context, state) => const AdminShell(),
      ),
    ],
  );
});
