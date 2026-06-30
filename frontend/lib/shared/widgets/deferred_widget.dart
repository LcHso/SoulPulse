import 'package:flutter/material.dart';

/// A widget that handles deferred (code-split) library loading for Flutter web.
///
/// Wraps a deferred import's `loadLibrary()` call and displays a loading
/// indicator until the library chunk is downloaded and ready.
/// Subsequent navigations to the same route are instant since `loadLibrary()`
/// is a no-op after the first successful load.
class DeferredWidget extends StatefulWidget {
  /// The deferred library's `loadLibrary` function (e.g., `gallery.loadLibrary`).
  final Future<void> Function() libraryLoader;

  /// Builder that constructs the actual page widget after the library is loaded.
  final WidgetBuilder builder;

  const DeferredWidget({
    super.key,
    required this.libraryLoader,
    required this.builder,
  });

  /// Preloads a deferred library without building the widget.
  /// Useful for prefetching on hover or predictive navigation.
  static Future<void> preload(Future<void> Function() libraryLoader) {
    return libraryLoader();
  }

  @override
  State<DeferredWidget> createState() => _DeferredWidgetState();
}

class _DeferredWidgetState extends State<DeferredWidget> {
  late Future<void> _libraryFuture;

  @override
  void initState() {
    super.initState();
    _libraryFuture = widget.libraryLoader();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<void>(
      future: _libraryFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.done) {
          if (snapshot.hasError) {
            return Scaffold(
              body: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error_outline, size: 48, color: Colors.red),
                    const SizedBox(height: 16),
                    Text(
                      '加载失败，请重试',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 16),
                    FilledButton(
                      onPressed: () {
                        setState(() {
                          _libraryFuture = widget.libraryLoader();
                        });
                      },
                      child: const Text('重试'),
                    ),
                  ],
                ),
              ),
            );
          }
          return widget.builder(context);
        }
        return const Scaffold(
          body: Center(
            child: CircularProgressIndicator(),
          ),
        );
      },
    );
  }
}
