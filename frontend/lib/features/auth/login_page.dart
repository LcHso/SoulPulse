// ============================================================================
// SoulPulse 登录/注册页面
// ============================================================================
//
// 本文件提供用户登录和注册的统一页面，包含：
// - 登录表单（邮箱、密码）
// - 注册表单（邮箱、密码、昵称、性别、偏好设置）
// - 登录/注册模式切换
// - 错误信息展示
// - 加载状态指示
//
// 主要组件：
// - LoginPage: 页面根组件（ConsumerStatefulWidget）
// - _LoginPageState: 页面状态管理类
//
// 功能说明：
// - 用户可选择登录或注册模式
// - 注册成功后自动登录
// - 登录成功后导航到信息流页面
//
// ============================================================================

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/providers/auth_provider.dart';

/// 登录/注册页面组件
///
/// 继承 ConsumerStatefulWidget 以支持 Riverpod 状态管理。
/// 提供用户登录和注册的统一界面，可通过底部按钮切换模式。
class LoginPage extends ConsumerStatefulWidget {
  /// 构造函数
  const LoginPage({super.key});

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

/// 登录页面状态类
///
/// 管理：
/// - 表单输入控制器（邮箱、密码、昵称）
/// - 登录/注册模式切换状态
/// - 错误信息展示
/// - 性别和偏好选择状态
/// - 登录/注册提交逻辑
class _LoginPageState extends ConsumerState<LoginPage> {
  /// 邮箱输入控制器
  final _emailCtrl = TextEditingController();

  /// 密码输入控制器
  final _passwordCtrl = TextEditingController();

  /// 昵称输入控制器（仅注册时使用）
  final _nicknameCtrl = TextEditingController();

  /// 当前是否为注册模式
  ///
  /// false: 登录模式
  /// true: 注册模式
  bool _isRegister = false;

  /// 错误信息（登录/注册失败时显示）
  String? _error;

  /// 用户性别选择值
  ///
  /// 可选值：'not_specified', 'male', 'female', 'non_binary'
  String _gender = 'not_specified';

  /// 用户偏好性别（希望匹配的 AI 性别）
  ///
  /// 可选值：'male', 'female', 'both'
  String _orientation = 'male';

  /// 将异常转换为用户友好的错误信息
  String _friendlyError(Object e) {
    final raw = e.toString().toLowerCase();
    if (raw.contains('connection refused') ||
        raw.contains('socket') ||
        raw.contains('network') ||
        raw.contains('timeout') ||
        raw.contains('host')) {
      return 'Unable to connect to server. Please check your network.';
    }
    if (raw.contains('invalid email or password') ||
        raw.contains('401') ||
        raw.contains('incorrect') ||
        raw.contains('unauthorized')) {
      return 'Incorrect email or password.';
    }
    if (raw.contains('already registered') || raw.contains('already exists')) {
      return 'This email is already registered. Try logging in.';
    }
    final cleaned = e.toString().replaceAll('Exception: ', '');
    if (cleaned.length > 100) return 'Something went wrong. Please try again.';
    return cleaned;
  }

  /// 提交登录/注册表单
  ///
  /// 根据当前模式（登录/注册）调用相应的认证方法：
  /// - 登录模式：调用 authProvider.login()
  /// - 注册模式：调用 authProvider.register()，成功后自动登录
  ///
  /// 成功后导航到信息流页面，失败时显示错误信息
  Future<void> _submit() async {
    // 清除之前的错误信息
    setState(() => _error = null);

    try {
      if (_isRegister) {
        // 注册模式：调用注册 API
        await ref.read(authProvider.notifier).register(
              _emailCtrl.text.trim(),
              _passwordCtrl.text,
              _nicknameCtrl.text.trim().isEmpty
                  ? 'User' // 昵称默认值
                  : _nicknameCtrl.text.trim(),
              gender: _gender,
              orientation: _orientation,
            );
      } else {
        // 登录模式：调用登录 API
        await ref.read(authProvider.notifier).login(
              _emailCtrl.text.trim(),
              _passwordCtrl.text,
            );
      }

      // 登录/注册成功，导航到信息流页面
      if (mounted) context.go('/feed');
    } catch (e) {
      // 失败时显示用户友好的错误信息
      setState(() => _error = _friendlyError(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    // 监听认证状态（用于显示加载指示器）
    final authState = ref.watch(authProvider);

    // 获取当前主题模式（用于适配深色/浅色主题）
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      body: SafeArea(
        child: Center(
          // 使用 SingleChildScrollView 支持小屏幕设备
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // ================== 应用标题区域 ==================
                const SizedBox(height: 40),

                /// 应用名称标题
                ///
                /// 使用 Inter 字体，粗体样式
                Text(
                  'SoulPulse',
                  style: GoogleFonts.inter(
                    fontSize: 36,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -1, // 紧凑字距
                  ),
                ),

                const SizedBox(height: 8),

                /// 应用副标题
                ///
                /// 根据主题模式调整颜色
                Text(
                  'Your AI companion, redefined.',
                  style: GoogleFonts.inter(
                    fontSize: 14,
                    color: isDark ? Colors.grey[400] : Colors.grey[600],
                  ),
                ),

                const SizedBox(height: 40),

                // ================== 登录表单区域 ==================

                /// 邮箱输入框
                TextField(
                  controller: _emailCtrl,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(hintText: 'Email'),
                ),

                const SizedBox(height: 12),

                /// 密码输入框
                ///
                /// obscureText: true 隐藏密码内容
                TextField(
                  controller: _passwordCtrl,
                  obscureText: true,
                  decoration: const InputDecoration(hintText: 'Password'),
                ),

                // ================== 注册表单额外字段 ==================
                /// 仅在注册模式下显示
                if (_isRegister) ...[
                  const SizedBox(height: 12),

                  /// 昵称输入框
                  TextField(
                    controller: _nicknameCtrl,
                    decoration: const InputDecoration(hintText: 'Nickname'),
                  ),

                  const SizedBox(height: 12),

                  /// 性别选择下拉框
                  ///
                  /// 提供四种选项：不愿透露、男性、女性、非二元
                  DropdownButtonFormField<String>(
                    value: _gender,
                    decoration: const InputDecoration(labelText: 'Gender'),
                    items: const [
                      DropdownMenuItem(
                          value: 'not_specified',
                          child: Text('Prefer not to say')),
                      DropdownMenuItem(value: 'male', child: Text('Male')),
                      DropdownMenuItem(value: 'female', child: Text('Female')),
                      DropdownMenuItem(
                          value: 'non_binary', child: Text('Non-binary')),
                    ],
                    onChanged: (v) => setState(() => _gender = v!),
                  ),

                  const SizedBox(height: 12),

                  /// 偏好性别选择下拉框
                  ///
                  /// 用户希望匹配的 AI 性别类型
                  DropdownButtonFormField<String>(
                    value: _orientation,
                    decoration:
                        const InputDecoration(labelText: 'Interested in'),
                    items: const [
                      DropdownMenuItem(
                          value: 'male', child: Text('Male characters')),
                      DropdownMenuItem(
                          value: 'female', child: Text('Female characters')),
                      DropdownMenuItem(
                          value: 'both', child: Text('All characters')),
                    ],
                    onChanged: (v) => setState(() => _orientation = v!),
                  ),
                ],

                const SizedBox(height: 20),

                // ================== 错误信息展示 ==================
                /// 仅在有错误时显示
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(
                      _error!,
                      style: const TextStyle(color: Colors.red, fontSize: 13),
                    ),
                  ),

                // ================== 提交按钮 ==================
                /// 登录/注册按钮
                ///
                /// 加载时禁用按钮并显示进度指示器
                ElevatedButton(
                  onPressed: authState.isLoading ? null : _submit,
                  child: authState.isLoading
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : Text(_isRegister ? 'Sign Up' : 'Log In'),
                ),

                const SizedBox(height: 16),

                // ================== 模式切换区域 ==================
                /// 登录/注册模式切换
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    /// 提示文本
                    Text(
                      _isRegister
                          ? 'Already have an account?' // 注册模式
                          : "Don't have an account?", // 登录模式
                      style: TextStyle(
                        fontSize: 13,
                        color: isDark ? Colors.grey[400] : Colors.grey[600],
                      ),
                    ),

                    /// 切换按钮
                    TextButton(
                      onPressed: () =>
                          setState(() => _isRegister = !_isRegister),
                      child: Text(
                        _isRegister ? 'Log In' : 'Sign Up',
                        style: const TextStyle(
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF0095F6), // Instagram 蓝色
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
