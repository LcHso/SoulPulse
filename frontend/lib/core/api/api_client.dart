// ============================================================================
// SoulPulse HTTP API 客户端
// ============================================================================
//
// 本文件提供与 SoulPulse 后端服务器通信的 HTTP 客户端封装，包含：
// - 统一的请求头配置（认证令牌、Content-Type）
// - JWT 令牌的持久化存储与加载
// - 响应缓存机制（stale-while-revalidate 策略）
// - 图片 URL 重写功能（处理 localhost 到实际服务器地址的转换）
// - 401 未认证错误的统一处理回调
//
// 主要类：
// - UnauthorizedException: 401 错误异常类
// - ApiClient: 静态方法封装的 HTTP 客户端
// - _CacheEntry: 缓存条目内部类
//
// ============================================================================

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// 未认证异常类
///
/// 当服务器返回 401 状态码时抛出此异常，触发重定向到登录页面。
class UnauthorizedException implements Exception {
  /// 异常消息
  final String message;

  /// 构造函数，默认消息为 'Unauthorized'
  UnauthorizedException([this.message = 'Unauthorized']);

  @override
  String toString() => message;
}

/// SoulPulse HTTP API 客户端
///
/// 提供与后端 API 交互的静态方法集合，支持：
/// - GET/POST/PATCH/DELETE 请求
/// - 自动添加认证令牌到请求头
/// - 请求超时控制（15 秒）
/// - 响应缓存与 stale-while-revalidate 策略
/// - 图片 URL 重写
/// - 401 未认证错误统一处理
///
/// 使用示例：
/// ```dart
/// // GET 请求
/// final user = await ApiClient.get('/api/auth/me');
///
/// // POST 请求
/// final result = await ApiClient.post('/api/chat/send', {'message': 'Hello'});
///
/// // 登录状态检查
/// if (ApiClient.isLoggedIn) { ... }
/// ```
class ApiClient {
  /// API 服务器基础 URL
  ///
  /// 可通过编译时环境变量 API_BASE_URL 配置，默认为 localhost:8001
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8001',
  );

  /// WebSocket 服务器基础 URL
  ///
  /// 根据 baseUrl 自动转换协议：
  /// - https:// -> wss://
  /// - http:// -> ws://
  static String get wsBaseUrl {
    if (baseUrl.startsWith('https://')) {
      return baseUrl.replaceFirst('https://', 'wss://');
    }
    return baseUrl.replaceFirst('http://', 'ws://');
  }

  /// 用户认证令牌（JWT）
  static String? _token;

  /// 获取当前认证令牌
  static String? get token => _token;

  /// 简单的内存响应缓存
  ///
  /// 实现 stale-while-revalidate 策略：先返回缓存数据，后台刷新缓存
  static final Map<String, _CacheEntry> _cache = {};

  /// 缓存有效期（30 秒）
  static const _cacheTtl = Duration(seconds: 30);

  /// 401 未认证回调函数
  ///
  /// 由应用层设置，触发登出和重定向到登录页
  static void Function()? onUnauthorized;

  /// 从本地存储加载认证令牌
  ///
  /// 在应用启动时调用，恢复用户登录状态
  static Future<void> loadToken() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('access_token');
  }

  /// 保存认证令牌到内存和本地存储
  ///
  /// 在用户登录成功后调用
  ///
  /// [token] JWT 认证令牌字符串
  static Future<void> saveToken(String token) async {
    _token = token;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('access_token', token);
  }

  /// 清除认证令牌和缓存
  ///
  /// 在用户登出时调用，清除内存令牌和本地存储
  static Future<void> clearToken() async {
    _token = null;
    _cache.clear(); // 清除缓存数据
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('access_token');
  }

  /// 检查用户是否已登录
  ///
  /// 通过检查令牌是否存在来判断登录状态
  static bool get isLoggedIn => _token != null;

  /// 构造标准请求头
  ///
  /// 包含：
  /// - Content-Type: application/json
  /// - Authorization: Bearer {token}（如果已登录）
  static Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  /// 检查响应状态码是否为 401
  ///
  /// 如果是 401，触发 onUnauthorized 回调并抛出 UnauthorizedException
  ///
  /// [response] HTTP 响应对象
  static void _check401(http.Response response) {
    if (response.statusCode == 401) {
      onUnauthorized?.call();
      throw UnauthorizedException();
    }
  }

  /// 发送 POST 请求
  ///
  /// 用于创建资源或执行操作，如发送消息、创建帖子等
  ///
  /// [path] API 路径（如 '/api/chat/send'）
  /// [body] 请求体 JSON 数据
  ///
  /// 返回解析后的 JSON 响应数据
  static Future<Map<String, dynamic>> post(
      String path, Map<String, dynamic> body) async {
    // 发送 POST 请求，设置 15 秒超时
    final response = await http
        .post(Uri.parse('$baseUrl$path'),
            headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 15));

    _check401(response);

    // 处理错误响应
    if (response.statusCode >= 400) {
      final err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Request failed');
    }

    // 重写 URL 并返回响应数据
    return _rewriteUrls(jsonDecode(response.body)) as Map<String, dynamic>;
  }

  /// 发送 PUT 请求
  static Future<Map<String, dynamic>> put(
      String path, Map<String, dynamic> body) async {
    final response = await http
        .put(Uri.parse('$baseUrl$path'),
            headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 15));

    _check401(response);

    if (response.statusCode >= 400) {
      final err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Request failed');
    }

    return _rewriteUrls(jsonDecode(response.body)) as Map<String, dynamic>;
  }

  /// 发送 PATCH 请求
  ///
  /// 用于部分更新资源，如修改用户资料
  ///
  /// [path] API 路径
  /// [body] 更新数据 JSON
  ///
  /// 返回更新后的资源数据
  static Future<Map<String, dynamic>> patch(
      String path, Map<String, dynamic> body) async {
    final response = await http
        .patch(Uri.parse('$baseUrl$path'),
            headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 15));

    _check401(response);

    if (response.statusCode >= 400) {
      final err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Request failed');
    }

    return _rewriteUrls(jsonDecode(response.body)) as Map<String, dynamic>;
  }

  /// 发送 DELETE 请求
  ///
  /// 用于删除资源，如删除消息、取消点赞等
  ///
  /// [path] API 路径
  /// [body] 可选的请求体数据
  ///
  /// 返回响应数据
  static Future<Map<String, dynamic>> delete(String path,
      [Map<String, dynamic>? body]) async {
    // 构造 DELETE 请求
    final request = http.Request('DELETE', Uri.parse('$baseUrl$path'));
    request.headers.addAll(_headers);
    if (body != null) request.body = jsonEncode(body);

    // 发送请求并等待响应
    final streamed =
        await http.Client().send(request).timeout(const Duration(seconds: 15));
    final response = await http.Response.fromStream(streamed);

    _check401(response);

    if (response.statusCode >= 400) {
      final err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Request failed');
    }

    return jsonDecode(response.body);
  }

  /// 发送表单 POST 请求
  ///
  /// 用于发送 form-urlencoded 格式的请求，如登录接口
  ///
  /// [path] API 路径
  /// [fields] 表单字段键值对
  ///
  /// 返回响应数据
  static Future<Map<String, dynamic>> postForm(
      String path, Map<String, String> fields) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl$path'),
          headers: {'Content-Type': 'application/x-www-form-urlencoded'},
          body: fields,
        )
        .timeout(const Duration(seconds: 15));

    // NOTE: Do NOT call _check401 here. postForm is used for login,
    // where 401 means "wrong credentials" — not an expired session.
    // Let the status >= 400 handler parse the real error detail.
    if (response.statusCode >= 400) {
      final err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Request failed');
    }

    return jsonDecode(response.body);
  }

  /// 发送 GET 请求并返回列表数据
  ///
  /// 支持 stale-while-revalidate 缓存策略：
  /// - 如果缓存存在且未过期，立即返回缓存数据，后台刷新
  /// - 如果缓存不存在，发送请求获取数据并缓存
  ///
  /// [path] API 路径
  /// [useCache] 是否启用缓存，默认启用
  ///
  /// 返回解析后的列表数据
  static Future<List<dynamic>> getList(String path,
      {bool useCache = true}) async {
    // 缓存逻辑：先检查缓存，未过期则立即返回并后台刷新
    if (useCache) {
      final cached = _cache[path];
      if (cached != null && !cached.isExpired) {
        // 立即返回缓存数据，后台异步刷新缓存
        _refreshListCache(path);
        return cached.listData!;
      }
    }

    // 发送 GET 请求
    final response = await http
        .get(Uri.parse('$baseUrl$path'), headers: _headers)
        .timeout(const Duration(seconds: 15));

    _check401(response);

    if (response.statusCode >= 400) {
      throw Exception('Request failed');
    }

    // 解析响应并缓存
    final data = _rewriteUrls(jsonDecode(response.body)) as List<dynamic>;
    if (useCache) {
      _cache[path] = _CacheEntry.list(data);
    }
    return data;
  }

  /// 后台刷新列表缓存
  ///
  /// 静默执行，失败时不影响用户界面
  ///
  /// [path] API 路径
  static Future<void> _refreshListCache(String path) async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl$path'), headers: _headers)
          .timeout(const Duration(seconds: 15));
      if (response.statusCode < 400) {
        _cache[path] = _CacheEntry.list(
            _rewriteUrls(jsonDecode(response.body)) as List<dynamic>);
      }
    } catch (_) {
      // 后台刷新失败时静默处理
    }
  }

  /// 重写图片 URL
  ///
  /// 将硬编码的 localhost URL 转换为实际配置的服务器地址。
  /// 也处理相对路径（如 "/static/..."）。
  ///
  /// [originalUrl] 原始 URL 字符串
  ///
  /// 返回重写后的 URL
  static String proxyImageUrl(String originalUrl) {
    if (originalUrl.isEmpty) return '';

    // 相对路径：在前面添加 API 基础 URL
    if (originalUrl.startsWith('/')) {
      return '$baseUrl$originalUrl';
    }

    // 重写 localhost:8001 到实际服务器地址
    if (originalUrl.contains('localhost:8001')) {
      return originalUrl.replaceFirst(
          RegExp(r'https?://localhost:8001'), baseUrl);
    }

    // 重写 127.0.0.1:8001 到实际服务器地址
    if (originalUrl.contains('127.0.0.1:8001')) {
      return originalUrl.replaceFirst(
          RegExp(r'https?://127\.0\.0\.1:8001'), baseUrl);
    }

    return originalUrl;
  }

  /// 递归重写 JSON 对象中的所有 URL
  ///
  /// 处理嵌套的 Map 和 List 结构，自动转换所有包含 localhost 或相对路径的字符串
  ///
  /// [data] 解析后的 JSON 数据（可以是 String、Map 或 List）
  ///
  /// 返回处理后的数据
  static dynamic _rewriteUrls(dynamic data) {
    if (data is String) {
      // 检查字符串是否需要重写
      if (data.contains('localhost:8001') ||
          data.contains('127.0.0.1:8001') ||
          (data.startsWith('/static/') && !data.startsWith('http'))) {
        return proxyImageUrl(data);
      }
      return data;
    }
    if (data is Map<String, dynamic>) {
      // 递归处理 Map 的所有值
      return data.map((k, v) => MapEntry(k, _rewriteUrls(v)));
    }
    if (data is List) {
      // 递归处理 List 的所有元素
      return data.map(_rewriteUrls).toList();
    }
    return data;
  }

  /// 发送 GET 请求并返回 Map 数据
  ///
  /// 同样支持 stale-while-revalidate 缓存策略
  ///
  /// [path] API 路径
  /// [useCache] 是否启用缓存，默认启用
  ///
  /// 返回解析后的 Map 数据
  static Future<Map<String, dynamic>> get(String path,
      {bool useCache = true}) async {
    // 缓存逻辑
    if (useCache) {
      final cached = _cache[path];
      if (cached != null && !cached.isExpired) {
        _refreshMapCache(path);
        return cached.mapData!;
      }
    }

    final response = await http
        .get(Uri.parse('$baseUrl$path'), headers: _headers)
        .timeout(const Duration(seconds: 15));

    _check401(response);

    if (response.statusCode >= 400) {
      throw Exception('Request failed');
    }

    final data =
        _rewriteUrls(jsonDecode(response.body)) as Map<String, dynamic>;
    if (useCache) {
      _cache[path] = _CacheEntry.map(data);
    }
    return data;
  }

  /// 后台刷新 Map 缓存
  ///
  /// [path] API 路径
  static Future<void> _refreshMapCache(String path) async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl$path'), headers: _headers)
          .timeout(const Duration(seconds: 15));
      if (response.statusCode < 400) {
        _cache[path] = _CacheEntry.map(
            _rewriteUrls(jsonDecode(response.body)) as Map<String, dynamic>);
      }
    } catch (_) {}
  }

  /// 清除缓存
  ///
  /// 可清除全部缓存或指定路径前缀的缓存
  ///
  /// [pathPrefix] 可选的路径前缀，用于部分清除
  static void invalidateCache([String? pathPrefix]) {
    if (pathPrefix == null) {
      // 清除全部缓存
      _cache.clear();
    } else {
      // 清除指定前缀的缓存条目
      _cache.removeWhere((key, _) => key.startsWith(pathPrefix));
    }
  }
}

/// 缓存条目内部类
///
/// 存储缓存数据及其创建时间，支持列表和 Map 两种数据类型
class _CacheEntry {
  /// 列表类型缓存数据
  final List<dynamic>? listData;

  /// Map 类型缓存数据
  final Map<String, dynamic>? mapData;

  /// 缓存创建时间
  final DateTime createdAt;

  /// 创建列表类型缓存条目
  _CacheEntry.list(this.listData)
      : mapData = null,
        createdAt = DateTime.now();

  /// 创建 Map 类型缓存条目
  _CacheEntry.map(this.mapData)
      : listData = null,
        createdAt = DateTime.now();

  /// 检查缓存是否过期
  ///
  /// 缓存超过 30 秒后视为过期
  bool get isExpired =>
      DateTime.now().difference(createdAt) > ApiClient._cacheTtl;
}
