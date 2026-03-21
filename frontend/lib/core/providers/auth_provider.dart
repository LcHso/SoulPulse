import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/api_client.dart';
import '../services/local_notification_service.dart';

/// Auth state: tracks current user data and login status.
class AuthState {
  final bool isLoggedIn;
  final Map<String, dynamic>? user;
  final bool isLoading;

  const AuthState({this.isLoggedIn = false, this.user, this.isLoading = false});

  AuthState copyWith(
      {bool? isLoggedIn, Map<String, dynamic>? user, bool? isLoading}) {
    return AuthState(
      isLoggedIn: isLoggedIn ?? this.isLoggedIn,
      user: user ?? this.user,
      isLoading: isLoading ?? this.isLoading,
    );
  }
}

class AuthNotifier extends Notifier<AuthState> {
  @override
  AuthState build() {
    return AuthState(isLoggedIn: ApiClient.isLoggedIn);
  }

  Future<void> login(String email, String password) async {
    state = state.copyWith(isLoading: true);
    try {
      final result = await ApiClient.postForm('/api/auth/login', {
        'username': email,
        'password': password,
      });
      await ApiClient.saveToken(result['access_token']);
      final user = await ApiClient.get('/api/auth/me', useCache: false);
      state = AuthState(isLoggedIn: true, user: user);
      // Start notification polling after login
      if (!kIsWeb) LocalNotificationService.startPolling();
    } catch (e) {
      state = state.copyWith(isLoading: false);
      rethrow;
    }
  }

  Future<void> register(String email, String password, String nickname,
      {String gender = 'not_specified', String orientation = 'male'}) async {
    state = state.copyWith(isLoading: true);
    try {
      await ApiClient.post('/api/auth/register', {
        'email': email,
        'password': password,
        'nickname': nickname,
        'gender': gender,
        'orientation_preference': orientation,
      });
      // Auto-login after registration
      await login(email, password);
    } catch (e) {
      state = state.copyWith(isLoading: false);
      rethrow;
    }
  }

  Future<void> loadUser() async {
    if (!ApiClient.isLoggedIn) return;
    try {
      final user = await ApiClient.get('/api/auth/me', useCache: false);
      state = AuthState(isLoggedIn: true, user: user);
    } catch (_) {}
  }

  Future<void> updateProfile(Map<String, dynamic> updates) async {
    final user = await ApiClient.patch('/api/auth/profile', updates);
    state = AuthState(isLoggedIn: true, user: user);
  }

  Future<void> logout() async {
    if (!kIsWeb) LocalNotificationService.stopPolling();
    await ApiClient.clearToken();
    state = const AuthState(isLoggedIn: false);
  }
}

final authProvider =
    NotifierProvider<AuthNotifier, AuthState>(AuthNotifier.new);

/// Derived provider: only emits when login status changes.
/// Router should watch this, not the full authProvider,
/// to avoid resetting navigation when user data refreshes.
final isLoggedInProvider = Provider<bool>((ref) {
  return ref.watch(authProvider.select((s) => s.isLoggedIn));
});
