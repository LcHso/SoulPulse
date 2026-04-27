// ============================================================================
// SoulPulse 认证状态管理 Provider
// ============================================================================
//
// 本文件使用 Riverpod 管理用户认证状态，包含：
// - 用户登录/注册/登出操作
// - 用户信息的加载与更新
// - 登录状态的派生 Provider（用于路由守卫）
// - 管理员状态的派生 Provider（用于权限控制）
//
// 主要类：
// - AuthState: 认证状态数据类
// - AuthNotifier: 认证状态管理器
//
// Provider：
// - authProvider: 主认证状态 Provider
// - isLoggedInProvider: 登录状态派生 Provider
// - isAdminProvider: 管理员状态派生 Provider
//
// ============================================================================

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../api/api_client.dart';
import '../services/local_notification_service.dart';

/// 认证状态数据类
///
/// 跟踪当前用户的登录状态、用户数据和加载状态。
/// 使用不可变设计，通过 copyWith 方法创建新状态。
class AuthState {
  /// 是否已登录
  final bool isLoggedIn;

  /// 当前用户数据（包含 id, email, nickname, is_admin 等字段）
  final Map<String, dynamic>? user;

  /// 是否正在加载（用于显示加载指示器）
  final bool isLoading;

  /// 构造函数
  ///
  /// 默认状态：未登录、无用户数据、不在加载
  const AuthState({this.isLoggedIn = false, this.user, this.isLoading = false});

  /// 创建状态副本
  ///
  /// 用于部分更新状态字段
  ///
  /// [isLoggedIn] 新的登录状态
  /// [user] 新的用户数据
  /// [isLoading] 新的加载状态
  ///
  /// 返回新的 AuthState 对象
  AuthState copyWith(
      {bool? isLoggedIn, Map<String, dynamic>? user, bool? isLoading}) {
    return AuthState(
      isLoggedIn: isLoggedIn ?? this.isLoggedIn,
      user: user ?? this.user,
      isLoading: isLoading ?? this.isLoading,
    );
  }

  /// 检查当前用户是否为管理员
  ///
  /// 通过检查 user['is_admin'] 字段判断
  bool get isAdmin {
    if (user == null) return false;
    return user!['is_admin'] == 1;
  }
}

/// 认证状态管理器
///
/// 继承 Riverpod 的 Notifier 类，提供认证相关的业务逻辑方法：
/// - login: 用户登录
/// - register: 用户注册
/// - loadUser: 加载用户信息
/// - updateProfile: 更新用户资料
/// - logout: 用户登出
class AuthNotifier extends Notifier<AuthState> {
  @override
  AuthState build() {
    // 初始状态：根据 ApiClient 的登录状态初始化
    return AuthState(isLoggedIn: ApiClient.isLoggedIn);
  }

  /// 用户登录
  ///
  /// 执行以下步骤：
  /// 1. 设置加载状态
  /// 2. 调用登录 API
  /// 3. 保存认证令牌
  /// 4. 加载用户信息
  /// 5. 更新登录状态
  /// 6. 启动通知轮询服务
  ///
  /// [email] 用户邮箱
  /// [password] 用户密码
  ///
  /// 抛出异常时更新状态并重新抛出
  Future<void> login(String email, String password) async {
    // 设置加载状态
    state = state.copyWith(isLoading: true);

    try {
      // 调用登录 API（使用 form-urlencoded 格式）
      final result = await ApiClient.postForm('/api/auth/login', {
        'username': email,
        'password': password,
      });

      // 保存 JWT 令牌到本地存储
      await ApiClient.saveToken(result['access_token']);

      // 加载用户详细信息
      final user = await ApiClient.get('/api/auth/me', useCache: false);

      // 更新认证状态为已登录
      state = AuthState(isLoggedIn: true, user: user);

      // 启动通知轮询服务
      LocalNotificationService.startPolling();
    } catch (e) {
      // 登录失败，更新加载状态并重新抛出异常
      state = state.copyWith(isLoading: false);
      rethrow;
    }
  }

  /// 检查用户是否需要完成引导流程
  ///
  /// 返回 true 表示需要引导，false 表示已完成引导
  Future<bool> needsOnboarding() async {
    final prefs = await SharedPreferences.getInstance();
    return !(prefs.getBool('onboarding_complete') ?? false);
  }

  /// 标记引导流程已完成
  Future<void> completeOnboarding() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('onboarding_complete', true);
  }

  /// 用户注册
  ///
  /// 执行以下步骤：
  /// 1. 设置加载状态
  /// 2. 调用注册 API
  /// 3. 自动登录新注册用户
  ///
  /// [email] 用户邮箱
  /// [password] 用户密码
  /// [nickname] 用户昵称
  /// [gender] 用户性别（默认 'not_specified'）
  /// [orientation] 用户偏好性别（默认 'male'）
  ///
  /// 抛出异常时更新状态并重新抛出
  Future<void> register(String email, String password, String nickname,
      {String gender = 'not_specified', String orientation = 'male'}) async {
    // 设置加载状态
    state = state.copyWith(isLoading: true);

    try {
      // 调用注册 API
      await ApiClient.post('/api/auth/register', {
        'email': email,
        'password': password,
        'nickname': nickname,
        'gender': gender,
        'orientation_preference': orientation,
      });

      // 注册成功后自动登录
      await login(email, password);
    } catch (e) {
      // 注册失败，更新加载状态并重新抛出异常
      state = state.copyWith(isLoading: false);
      rethrow;
    }
  }

  /// 加载已登录用户的信息
  ///
  /// 在应用启动或恢复登录状态后调用，
  /// 获取用户的详细信息并更新状态
  Future<void> loadUser() async {
    // 检查是否有有效令牌
    if (!ApiClient.isLoggedIn) return;

    try {
      // 获取用户信息
      final user = await ApiClient.get('/api/auth/me', useCache: false);

      // 更新认证状态
      state = AuthState(isLoggedIn: true, user: user);
    } catch (_) {
      // 加载失败时静默处理
    }
  }

  /// 更新用户资料
  ///
  /// 调用 PATCH API 更新用户信息，并同步更新本地状态
  ///
  /// [updates] 要更新的字段键值对
  Future<void> updateProfile(Map<String, dynamic> updates) async {
    // 调用更新 API
    final user = await ApiClient.patch('/api/auth/profile', updates);

    // 更新本地状态
    state = AuthState(isLoggedIn: true, user: user);
  }

  /// 用户登出
  ///
  /// 执行以下步骤：
  /// 1. 停止通知轮询服务
  /// 2. 清除认证令牌和缓存
  /// 3. 更新状态为未登录
  Future<void> logout() async {
    // 停止通知轮询服务
    LocalNotificationService.stopPolling();

    // 清除令牌和缓存
    await ApiClient.clearToken();

    // 更新状态为未登录
    state = const AuthState(isLoggedIn: false);
  }
}

/// 主认证状态 Provider
///
/// 使用 NotifierProvider 创建 AuthNotifier 实例
final authProvider =
    NotifierProvider<AuthNotifier, AuthState>(AuthNotifier.new);

/// 登录状态派生 Provider
///
/// 仅在登录状态变化时触发通知。
/// 路由守卫应监听此 Provider，而非完整的 authProvider，
/// 以避免用户数据刷新时重置导航状态。
///
/// 使用 select 方法仅选择 isLoggedIn 字段
final isLoggedInProvider = Provider<bool>((ref) {
  return ref.watch(authProvider.select((s) => s.isLoggedIn));
});

/// 管理员状态派生 Provider
///
/// 用于管理员路由的访问控制，
/// 检查用户是否具有管理员权限
final isAdminProvider = Provider<bool>((ref) {
  return ref.watch(authProvider).isAdmin;
});
