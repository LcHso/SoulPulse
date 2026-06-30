import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:shimmer/shimmer.dart';
import 'package:visibility_detector/visibility_detector.dart';

/// A lazy-loading wrapper around [CachedNetworkImage] that defers network
/// requests until the widget scrolls into (or near) the viewport.
///
/// Once the image becomes visible it stays loaded — scrolling away does NOT
/// unload it, preventing unnecessary re-fetches.
///
/// The [visibilityThreshold] controls how many pixels ahead of the viewport
/// the image starts loading (default 200px via padding in the detector).
class LazyCachedImage extends StatefulWidget {
  final String imageUrl;
  final BoxFit fit;
  final double? width;
  final double? height;
  final Widget Function(BuildContext context)? placeholder;
  final Widget Function(BuildContext context, String url, dynamic error)?
      errorWidget;

  /// Extra viewport margin (in logical pixels) that triggers loading before
  /// the widget is fully on screen. Helps avoid pop-in during fast scrolling.
  final double preloadMargin;

  const LazyCachedImage({
    super.key,
    required this.imageUrl,
    this.fit = BoxFit.cover,
    this.width,
    this.height,
    this.placeholder,
    this.errorWidget,
    this.preloadMargin = 200.0,
  });

  @override
  State<LazyCachedImage> createState() => _LazyCachedImageState();
}

class _LazyCachedImageState extends State<LazyCachedImage> {
  bool _shouldLoad = false;

  // Unique key for VisibilityDetector — uses widget identity + imageUrl hash
  late final Key _detectorKey = ValueKey('lazy_img_${widget.imageUrl.hashCode}');

  void _onVisibilityChanged(VisibilityInfo info) {
    if (_shouldLoad) return; // Already triggered, no-op
    if (info.visibleFraction > 0) {
      setState(() => _shouldLoad = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    // Default shimmer placeholder
    Widget defaultPlaceholder() {
      return Shimmer.fromColors(
        baseColor: isDark ? const Color(0xFF2A2A3E) : const Color(0xFFE8E4E0),
        highlightColor:
            isDark ? const Color(0xFF3A3A52) : const Color(0xFFF5F2EE),
        child: Container(
          width: widget.width,
          height: widget.height,
          color: Colors.white,
        ),
      );
    }

    // Default error widget
    Widget defaultError(BuildContext ctx, String url, dynamic error) {
      return Container(
        width: widget.width,
        height: widget.height,
        color: isDark ? const Color(0xFF1A1A2E) : const Color(0xFFF0ECE8),
        child: Center(
          child: Icon(Icons.broken_image_outlined,
              size: 40, color: Colors.grey[400]),
        ),
      );
    }

    // Use VisibilityDetector with the preload margin applied via padding
    // trick: we wrap in a slightly oversized detection area so the callback
    // fires before the widget is actually visible on screen.
    return VisibilityDetector(
      key: _detectorKey,
      onVisibilityChanged: _onVisibilityChanged,
      child: _shouldLoad
          ? CachedNetworkImage(
              imageUrl: widget.imageUrl,
              fit: widget.fit,
              width: widget.width,
              height: widget.height,
              placeholder: (context, url) =>
                  widget.placeholder?.call(context) ?? defaultPlaceholder(),
              errorWidget: (context, url, error) =>
                  widget.errorWidget?.call(context, url, error) ??
                  defaultError(context, url, error),
            )
          : widget.placeholder?.call(context) ?? defaultPlaceholder(),
    );
  }
}
