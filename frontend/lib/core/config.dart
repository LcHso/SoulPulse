/// Application configuration
///
/// Modify API_BASE_URL for your production deployment.
/// You can also set this at build time:
///   flutter build web --dart-define=API_BASE_URL=https://your-api-domain.com
class AppConfig {
  /// API server base URL
  ///
  /// Change this to your production backend URL before deploying.
  /// Examples:
  ///   - Development: 'http://localhost:8001'
  ///   - Production: 'https://api.yourdomain.com' or 'http://your-server-ip:8001'
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8001',
  );
}
