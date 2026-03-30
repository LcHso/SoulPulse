import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/api/api_client.dart';
import 'core/theme/app_theme.dart';
import 'core/router/app_router.dart';
import 'core/providers/auth_provider.dart';
import 'core/services/local_notification_service.dart';
import 'core/services/fcm_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await ApiClient.loadToken();

  // Initialize local notifications (Android only)
  if (!kIsWeb) {
    await LocalNotificationService.init();
  }

  // Initialize FCM (will gracefully fail if not configured)
  if (!kIsWeb) {
    try {
      await FcmService().initialize();
      print('[Main] FCM initialized');
    } catch (e) {
      print('[Main] FCM initialization skipped: $e');
      // FCM will fall back to local notification polling
    }
  }

  // Global error handling
  FlutterError.onError = (details) {
    FlutterError.presentError(details);
  };

  runZonedGuarded(
    () => runApp(const ProviderScope(child: SoulPulseApp())),
    (error, stack) {
      debugPrint('Uncaught error: $error\n$stack');
    },
  );
}

class SoulPulseApp extends ConsumerStatefulWidget {
  const SoulPulseApp({super.key});

  @override
  ConsumerState<SoulPulseApp> createState() => _SoulPulseAppState();
}

class _SoulPulseAppState extends ConsumerState<SoulPulseApp> {
  StreamSubscription<String>? _notifTapSub;

  @override
  void initState() {
    super.initState();
    // Set up 401 handler
    ApiClient.onUnauthorized = () {
      ref.read(authProvider.notifier).logout();
    };
    // Load user data if logged in
    if (ApiClient.isLoggedIn) {
      Future.microtask(() => ref.read(authProvider.notifier).loadUser());
      // Start notification polling on Android
      if (!kIsWeb) {
        LocalNotificationService.startPolling();
      }
    }

    // Listen for notification taps (Android)
    if (!kIsWeb) {
      _notifTapSub =
          LocalNotificationService.onNotificationTap.listen(_handleNotifTap);
      // Check if app was launched from a notification tap
      final pending = LocalNotificationService.consumePendingPayload();
      if (pending != null && pending.isNotEmpty) {
        Future.microtask(() => _handleNotifTap(pending));
      }
    }
  }

  @override
  void dispose() {
    _notifTapSub?.cancel();
    LocalNotificationService.dispose();
    super.dispose();
  }

  void _handleNotifTap(String payload) {
    if (payload.isEmpty) return;
    try {
      final data = jsonDecode(payload) as Map<String, dynamic>;
      final type = data['type'] as String? ?? '';
      Map<String, dynamic>? meta;
      try {
        final dj = data['data_json'] as String?;
        if (dj != null && dj.isNotEmpty) {
          meta = jsonDecode(dj) as Map<String, dynamic>;
        }
      } catch (_) {}

      final router = ref.read(routerProvider);

      switch (type) {
        case 'comment_reply':
        case 'new_post':
          // Navigate to notifications page which handles post detail navigation
          router.push('/notifications');
          break;
        case 'proactive_dm':
          if (meta != null && meta['ai_id'] != null) {
            final aiId = meta['ai_id'] as int;
            final aiName = meta['ai_name'] as String? ?? 'AI';
            router.push('/chat/$aiId?name=${Uri.encodeComponent(aiName)}');
          } else {
            router.push('/notifications');
          }
          break;
        case 'intimacy_upgrade':
          if (meta != null && meta['ai_id'] != null) {
            final aiId = meta['ai_id'] as int;
            final aiName = meta['ai_name'] as String? ?? 'AI';
            router.push('/ai/$aiId?name=${Uri.encodeComponent(aiName)}');
          } else {
            router.push('/notifications');
          }
          break;
        default:
          router.push('/notifications');
      }
    } catch (_) {
      // Fallback: open notifications page
      try {
        ref.read(routerProvider).push('/notifications');
      } catch (_) {}
    }
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      title: 'SoulPulse',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      routerConfig: router,
    );
  }
}
