import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Thrown when server returns 401, triggers redirect to login.
class UnauthorizedException implements Exception {
  final String message;
  UnauthorizedException([this.message = 'Unauthorized']);
}

class ApiClient {
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8001',
  );

  static String get wsBaseUrl {
    if (baseUrl.startsWith('https://')) {
      return baseUrl.replaceFirst('https://', 'wss://');
    }
    return baseUrl.replaceFirst('http://', 'ws://');
  }

  static String? _token;
  static String? get token => _token;

  // Simple in-memory response cache (stale-while-revalidate pattern)
  static final Map<String, _CacheEntry> _cache = {};
  static const _cacheTtl = Duration(seconds: 30);

  // Callback for 401 handling — set by the app shell
  static void Function()? onUnauthorized;

  static Future<void> loadToken() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('access_token');
  }

  static Future<void> saveToken(String token) async {
    _token = token;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('access_token', token);
  }

  static Future<void> clearToken() async {
    _token = null;
    _cache.clear();
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('access_token');
  }

  static bool get isLoggedIn => _token != null;

  static Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  static void _check401(http.Response response) {
    if (response.statusCode == 401) {
      onUnauthorized?.call();
      throw UnauthorizedException();
    }
  }

  static Future<Map<String, dynamic>> post(
      String path, Map<String, dynamic> body) async {
    final response = await http
        .post(Uri.parse('$baseUrl$path'),
            headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 15));
    _check401(response);
    if (response.statusCode >= 400) {
      final err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Request failed');
    }
    return jsonDecode(response.body);
  }

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
    return jsonDecode(response.body);
  }

  static Future<Map<String, dynamic>> delete(String path,
      [Map<String, dynamic>? body]) async {
    final request = http.Request('DELETE', Uri.parse('$baseUrl$path'));
    request.headers.addAll(_headers);
    if (body != null) request.body = jsonEncode(body);
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

  static Future<Map<String, dynamic>> postForm(
      String path, Map<String, String> fields) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl$path'),
          headers: {'Content-Type': 'application/x-www-form-urlencoded'},
          body: fields,
        )
        .timeout(const Duration(seconds: 15));
    _check401(response);
    if (response.statusCode >= 400) {
      final err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Request failed');
    }
    return jsonDecode(response.body);
  }

  /// GET that returns a list. Supports stale-while-revalidate caching.
  static Future<List<dynamic>> getList(String path,
      {bool useCache = true}) async {
    if (useCache) {
      final cached = _cache[path];
      if (cached != null && !cached.isExpired) {
        // Return cache immediately, refresh in background
        _refreshListCache(path);
        return cached.listData!;
      }
    }

    final response = await http
        .get(Uri.parse('$baseUrl$path'), headers: _headers)
        .timeout(const Duration(seconds: 15));
    _check401(response);
    if (response.statusCode >= 400) {
      throw Exception('Request failed');
    }
    final data = jsonDecode(response.body) as List<dynamic>;
    if (useCache) {
      _cache[path] = _CacheEntry.list(data);
    }
    return data;
  }

  static Future<void> _refreshListCache(String path) async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl$path'), headers: _headers)
          .timeout(const Duration(seconds: 15));
      if (response.statusCode < 400) {
        _cache[path] =
            _CacheEntry.list(jsonDecode(response.body) as List<dynamic>);
      }
    } catch (_) {
      // Silent background refresh failure
    }
  }

  static String proxyImageUrl(String originalUrl) {
    if (originalUrl.isEmpty) return '';
    return originalUrl;
  }

  /// GET that returns a map. Supports stale-while-revalidate caching.
  static Future<Map<String, dynamic>> get(String path,
      {bool useCache = true}) async {
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
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    if (useCache) {
      _cache[path] = _CacheEntry.map(data);
    }
    return data;
  }

  static Future<void> _refreshMapCache(String path) async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl$path'), headers: _headers)
          .timeout(const Duration(seconds: 15));
      if (response.statusCode < 400) {
        _cache[path] =
            _CacheEntry.map(jsonDecode(response.body) as Map<String, dynamic>);
      }
    } catch (_) {}
  }

  /// Invalidate cache for a specific path prefix.
  static void invalidateCache([String? pathPrefix]) {
    if (pathPrefix == null) {
      _cache.clear();
    } else {
      _cache.removeWhere((key, _) => key.startsWith(pathPrefix));
    }
  }
}

class _CacheEntry {
  final List<dynamic>? listData;
  final Map<String, dynamic>? mapData;
  final DateTime createdAt;

  _CacheEntry.list(this.listData)
      : mapData = null,
        createdAt = DateTime.now();
  _CacheEntry.map(this.mapData)
      : listData = null,
        createdAt = DateTime.now();

  bool get isExpired =>
      DateTime.now().difference(createdAt) > ApiClient._cacheTtl;
}
