import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiClient {
  // Change this to your backend URL
  static const String baseUrl = 'http://localhost:8001'; // Local dev
  // static const String baseUrl = 'http://localhost:8000'; // Web / iOS sim

  static String? _token;

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
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('access_token');
  }

  static bool get isLoggedIn => _token != null;

  static Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  static Future<Map<String, dynamic>> post(
      String path, Map<String, dynamic> body) async {
    final response = await http.post(
      Uri.parse('$baseUrl$path'),
      headers: _headers,
      body: jsonEncode(body),
    );
    if (response.statusCode >= 400) {
      final err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Request failed');
    }
    return jsonDecode(response.body);
  }

  static Future<Map<String, dynamic>> postForm(
      String path, Map<String, String> fields) async {
    final response = await http.post(
      Uri.parse('$baseUrl$path'),
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: fields,
    );
    if (response.statusCode >= 400) {
      final err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Request failed');
    }
    return jsonDecode(response.body);
  }

  static Future<List<dynamic>> getList(String path) async {
    final response = await http.get(
      Uri.parse('$baseUrl$path'),
      headers: _headers,
    );
    if (response.statusCode >= 400) {
      throw Exception('Request failed');
    }
    return jsonDecode(response.body);
  }

  static String proxyImageUrl(String originalUrl) {
    if (originalUrl.isEmpty) return '';
    return '$baseUrl/api/feed/image-proxy?url=${Uri.encodeComponent(originalUrl)}';
  }

  static Future<Map<String, dynamic>> get(String path) async {
    final response = await http.get(
      Uri.parse('$baseUrl$path'),
      headers: _headers,
    );
    if (response.statusCode >= 400) {
      throw Exception('Request failed');
    }
    return jsonDecode(response.body);
  }
}
