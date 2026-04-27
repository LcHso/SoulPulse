import 'package:flutter/material.dart';

/// A floating toast animation that shows "+X intimacy" feedback.
///
/// Displays a floating heart with intimacy delta that animates upward
/// and fades out over 1.5 seconds.
class IntimacyToast {
  /// Shows the intimacy toast at the bottom center of the screen.
  ///
  /// [context] BuildContext for the overlay
  /// [delta] The intimacy change amount (e.g., 1.0 or 0.3)
  /// [color] Optional color for the text (defaults to pink)
  static void show(
    BuildContext context, {
    required double delta,
    Color? color,
  }) {
    final overlay = Overlay.of(context);
    final entry = OverlayEntry(
      builder: (context) => _IntimacyToastWidget(
        delta: delta,
        color: color ?? const Color(0xFFE91E63),
      ),
    );

    overlay.insert(entry);

    // Auto-remove after animation completes
    Future.delayed(const Duration(milliseconds: 1500), () {
      entry.remove();
    });
  }
}

class _IntimacyToastWidget extends StatefulWidget {
  final double delta;
  final Color color;

  const _IntimacyToastWidget({
    required this.delta,
    required this.color,
  });

  @override
  State<_IntimacyToastWidget> createState() => _IntimacyToastWidgetState();
}

class _IntimacyToastWidgetState extends State<_IntimacyToastWidget>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;
  late Animation<double> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    );

    _fadeAnimation = Tween<double>(begin: 1.0, end: 0.0).animate(
      CurvedAnimation(
        parent: _controller,
        curve: const Interval(0.5, 1.0, curve: Curves.easeOut),
      ),
    );

    _slideAnimation = Tween<double>(begin: 0.0, end: -60.0).animate(
      CurvedAnimation(
        parent: _controller,
        curve: Curves.easeOut,
      ),
    );

    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Positioned(
      bottom: 100,
      left: 0,
      right: 0,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          return Opacity(
            opacity: _fadeAnimation.value,
            child: Transform.translate(
              offset: Offset(0, _slideAnimation.value),
              child: child,
            ),
          );
        },
        child: Center(
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.black.withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.favorite,
                  color: widget.color,
                  size: 18,
                ),
                const SizedBox(width: 6),
                Text(
                  '+${widget.delta.toStringAsFixed(1)} intimacy',
                  style: TextStyle(
                    color: widget.color,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
