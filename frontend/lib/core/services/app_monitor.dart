// ============================================================================
// SoulPulse App Monitor - Lightweight Error & Performance Tracking
// ============================================================================
//
// Provides local error tracking and performance monitoring without external
// dependencies (no Firebase/Sentry setup required). Designed for easy extension
// to send data to a remote backend or integrate with Sentry/Firebase later.
//
// Usage:
//   AppMonitor.instance.recordError(error, stackTrace, context: 'chat');
//   AppMonitor.instance.startTrace('page_load');
//   AppMonitor.instance.endTrace('page_load');
//
// ============================================================================

import 'dart:collection';
import 'package:flutter/foundation.dart';

// ---------------------------------------------------------------------------
// Error Reporter Interface
// ---------------------------------------------------------------------------

/// Abstract interface for external error reporting services.
///
/// Implement this to plug in Sentry, Firebase Crashlytics, or a custom backend.
///
/// TODO: To add Sentry integration:
///   1. Add `sentry_flutter` to pubspec.yaml
///   2. Create a class implementing [ErrorReporter]
///   3. Call `AppMonitor.instance.addReporter(SentryReporter(dsn: 'YOUR_DSN'))`
///   4. All errors will be forwarded automatically
abstract class ErrorReporter {
  /// Report an error to the external service.
  Future<void> reportError(ErrorRecord record);

  /// Report a performance metric.
  Future<void> reportPerformance(String name, Duration duration,
      {Map<String, String>? metadata});
}

// ---------------------------------------------------------------------------
// Data Models
// ---------------------------------------------------------------------------

/// A recorded error with context information.
class ErrorRecord {
  final dynamic error;
  final StackTrace? stackTrace;
  final String? context;
  final DateTime timestamp;
  final bool isFatal;

  ErrorRecord({
    required this.error,
    this.stackTrace,
    this.context,
    DateTime? timestamp,
    this.isFatal = false,
  }) : timestamp = timestamp ?? DateTime.now();

  @override
  String toString() {
    final ctx = context != null ? ' [$context]' : '';
    return '${timestamp.toIso8601String()}$ctx: $error';
  }
}

/// A completed performance trace.
class TraceRecord {
  final String name;
  final Duration duration;
  final DateTime timestamp;

  TraceRecord({
    required this.name,
    required this.duration,
    DateTime? timestamp,
  }) : timestamp = timestamp ?? DateTime.now();
}

/// Aggregated API endpoint statistics.
class ApiEndpointStats {
  final String endpoint;
  int callCount = 0;
  Duration totalDuration = Duration.zero;
  Duration? maxDuration;
  Duration? minDuration;
  int slowCallCount = 0; // Calls exceeding threshold

  ApiEndpointStats(this.endpoint);

  Duration get averageDuration =>
      callCount > 0 ? totalDuration ~/ callCount : Duration.zero;

  void record(Duration duration, {Duration slowThreshold = const Duration(seconds: 3)}) {
    callCount++;
    totalDuration += duration;
    if (maxDuration == null || duration > maxDuration!) maxDuration = duration;
    if (minDuration == null || duration < minDuration!) minDuration = duration;
    if (duration > slowThreshold) slowCallCount++;
  }
}

// ---------------------------------------------------------------------------
// AppMonitor Singleton
// ---------------------------------------------------------------------------

/// Lightweight application monitoring service.
///
/// Tracks errors, performance traces, and API call metrics locally.
/// Supports pluggable [ErrorReporter] instances for forwarding data
/// to external services (Sentry, Firebase, custom backend).
class AppMonitor {
  AppMonitor._();

  /// Singleton instance for global access.
  static final AppMonitor instance = AppMonitor._();

  // ---- Configuration ----

  /// Maximum number of error records to retain in memory.
  static const int _maxErrorRecords = 100;

  /// Maximum number of trace records to retain in memory.
  static const int _maxTraceRecords = 200;

  /// Threshold above which an API call is considered "slow".
  static const Duration slowApiThreshold = Duration(seconds: 3);

  // ---- State ----

  final List<ErrorReporter> _reporters = [];
  final Queue<ErrorRecord> _errors = Queue<ErrorRecord>();
  final Queue<TraceRecord> _traces = Queue<TraceRecord>();
  final Map<String, Stopwatch> _activeTraces = {};
  final Map<String, ApiEndpointStats> _apiStats = {};

  /// App startup timestamp (set at the very beginning of main()).
  DateTime? _appStartTime;

  /// Duration from main() start to first frame rendered.
  Duration? _startupDuration;

  // ---- Public Getters ----

  /// Duration of app startup (main → first frame), or null if not yet measured.
  Duration? get startupDuration => _startupDuration;

  /// Recent errors (oldest first).
  List<ErrorRecord> get recentErrors => _errors.toList();

  /// Recent performance traces (oldest first).
  List<TraceRecord> get recentTraces => _traces.toList();

  /// Per-endpoint API call statistics.
  Map<String, ApiEndpointStats> get apiStats => Map.unmodifiable(_apiStats);

  /// Convenience: page load times extracted from traces matching 'page_*'.
  Map<String, Duration> get pageLoadTimes {
    final map = <String, Duration>{};
    for (final trace in _traces) {
      if (trace.name.startsWith('page_')) {
        map[trace.name] = trace.duration;
      }
    }
    return map;
  }

  /// Convenience: API call durations from traces matching 'api_*'.
  Map<String, Duration> get apiCallTimes {
    final map = <String, Duration>{};
    for (final trace in _traces) {
      if (trace.name.startsWith('api_')) {
        map[trace.name] = trace.duration;
      }
    }
    return map;
  }

  // ---- Reporter Management ----

  /// Add an external reporter that receives all errors and performance data.
  ///
  /// TODO: Plug in Sentry/Firebase here:
  ///   AppMonitor.instance.addReporter(SentryReporter(dsn: 'YOUR_SENTRY_DSN'));
  void addReporter(ErrorReporter reporter) {
    _reporters.add(reporter);
  }

  /// Remove a previously added reporter.
  void removeReporter(ErrorReporter reporter) {
    _reporters.remove(reporter);
  }

  // ---- App Lifecycle ----

  /// Mark the start of app initialization. Call at the top of main().
  void markAppStart() {
    _appStartTime = DateTime.now();
  }

  /// Mark the first frame rendered. Call from a post-frame callback.
  void markFirstFrame() {
    if (_appStartTime != null && _startupDuration == null) {
      _startupDuration = DateTime.now().difference(_appStartTime!);
      if (kDebugMode) {
        debugPrint('[AppMonitor] Startup duration: ${_startupDuration!.inMilliseconds}ms');
      }
    }
  }

  // ---- Error Tracking ----

  /// Record an error.
  ///
  /// In debug mode, also prints to console. Forwards to all registered reporters.
  void recordError(
    dynamic error,
    StackTrace? stack, {
    String? context,
    bool fatal = false,
  }) {
    final record = ErrorRecord(
      error: error,
      stackTrace: stack,
      context: context,
      isFatal: fatal,
    );

    _errors.addLast(record);
    while (_errors.length > _maxErrorRecords) {
      _errors.removeFirst();
    }

    if (kDebugMode) {
      debugPrint('[AppMonitor] ERROR${context != null ? " [$context]" : ""}: $error');
      if (stack != null) {
        debugPrint(stack.toString().split('\n').take(8).join('\n'));
      }
    }

    // Forward to external reporters
    for (final reporter in _reporters) {
      reporter.reportError(record).catchError((_) {});
    }
  }

  /// Get recent errors, optionally filtered by context.
  List<ErrorRecord> getRecentErrors({String? context, int? limit}) {
    var list = _errors.toList();
    if (context != null) {
      list = list.where((e) => e.context == context).toList();
    }
    if (limit != null && list.length > limit) {
      list = list.sublist(list.length - limit);
    }
    return list;
  }

  // ---- Performance Tracing ----

  /// Start a named performance trace.
  void startTrace(String name) {
    _activeTraces[name] = Stopwatch()..start();
  }

  /// End a named trace and record its duration.
  ///
  /// Returns the duration if the trace existed, null otherwise.
  Duration? endTrace(String name) {
    final stopwatch = _activeTraces.remove(name);
    if (stopwatch == null) return null;

    stopwatch.stop();
    final duration = stopwatch.elapsed;

    final record = TraceRecord(name: name, duration: duration);
    _traces.addLast(record);
    while (_traces.length > _maxTraceRecords) {
      _traces.removeFirst();
    }

    if (kDebugMode) {
      debugPrint('[AppMonitor] TRACE "$name": ${duration.inMilliseconds}ms');
    }

    // Forward to reporters
    for (final reporter in _reporters) {
      reporter.reportPerformance(name, duration).catchError((_) {});
    }

    return duration;
  }

  /// Get the duration of a completed trace by name (most recent).
  Duration? getTrace(String name) {
    for (final trace in _traces.toList().reversed) {
      if (trace.name == name) return trace.duration;
    }
    return null;
  }

  // ---- API Performance Tracking ----

  /// Record an API call's duration for the given endpoint.
  ///
  /// Automatically logs slow requests in debug mode.
  void recordApiCall(String endpoint, Duration duration) {
    final stats = _apiStats.putIfAbsent(endpoint, () => ApiEndpointStats(endpoint));
    stats.record(duration, slowThreshold: slowApiThreshold);

    // Also store as a trace entry
    final record = TraceRecord(
      name: 'api_$endpoint',
      duration: duration,
    );
    _traces.addLast(record);
    while (_traces.length > _maxTraceRecords) {
      _traces.removeFirst();
    }

    if (duration > slowApiThreshold && kDebugMode) {
      debugPrint(
        '[AppMonitor] SLOW API: $endpoint took ${duration.inMilliseconds}ms '
        '(threshold: ${slowApiThreshold.inMilliseconds}ms)',
      );
    }
  }

  // ---- Utilities ----

  /// Clear all stored data (useful for logout or testing).
  void reset() {
    _errors.clear();
    _traces.clear();
    _activeTraces.clear();
    _apiStats.clear();
    _startupDuration = null;
    _appStartTime = null;
  }
}
