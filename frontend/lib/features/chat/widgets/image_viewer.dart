// ============================================================================
// ImageViewer — full-screen image viewer with pinch-to-zoom
// ============================================================================
//
// Displays a network image full-screen with:
//  • Pinch-to-zoom (via photo_view)
//  • Swipe-down or tap the × button to dismiss
//  • Hero animation from chat thumbnail
//  • Download / save action placeholder
// ============================================================================

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:photo_view/photo_view.dart';

/// Full-screen image viewer.
///
/// Open via [ImageViewer.show] as a transparent overlay page.
class ImageViewer extends StatelessWidget {
  /// The network URL of the image to display.
  final String imageUrl;

  /// Optional Hero tag that matches the thumbnail's Hero tag.
  final String? heroTag;

  const ImageViewer({
    super.key,
    required this.imageUrl,
    this.heroTag,
  });

  // ─── static helper ────────────────────────────────────────────────────────

  /// Push the viewer as a transparent overlay route.
  static Future<void> show(
    BuildContext context, {
    required String imageUrl,
    String? heroTag,
  }) {
    return Navigator.of(context).push(
      PageRouteBuilder<void>(
        opaque: false,
        barrierDismissible: true,
        barrierColor: Colors.black.withValues(alpha: 0.92),
        transitionDuration: const Duration(milliseconds: 250),
        pageBuilder: (ctx, _, __) =>
            ImageViewer(imageUrl: imageUrl, heroTag: heroTag),
        transitionsBuilder: (ctx, animation, _, child) =>
            FadeTransition(opacity: animation, child: child),
      ),
    );
  }

  // ─── build ────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: Stack(
        children: [
          // ── photo_view (supports pinch-zoom + double-tap) ────────────────
          GestureDetector(
            // Tap the dark background to close
            onVerticalDragEnd: (d) {
              if (d.primaryVelocity != null &&
                  d.primaryVelocity!.abs() > 600) {
                Navigator.of(context).pop();
              }
            },
            child: PhotoView(
              imageProvider: NetworkImage(imageUrl),
              heroAttributes: heroTag != null
                  ? PhotoViewHeroAttributes(tag: heroTag!)
                  : null,
              minScale: PhotoViewComputedScale.contained,
              maxScale: PhotoViewComputedScale.covered * 4,
              initialScale: PhotoViewComputedScale.contained,
              backgroundDecoration:
                  const BoxDecoration(color: Colors.transparent),
              loadingBuilder: (_, event) => Center(
                child: CircularProgressIndicator(
                  value: event?.expectedTotalBytes != null
                      ? (event!.cumulativeBytesLoaded /
                          event.expectedTotalBytes!)
                      : null,
                  color: Colors.white54,
                  strokeWidth: 2,
                ),
              ),
              errorBuilder: (_, __, ___) => const Center(
                child: Icon(
                    Icons.broken_image_outlined,
                    color: Colors.white54,
                    size: 64),
              ),
            ),
          ),

          // ── top bar: close + download ─────────────────────────────────────
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  // Close button
                  _CircleButton(
                    icon: Icons.close,
                    onTap: () => Navigator.of(context).pop(),
                  ),

                  // Download hint
                  _CircleButton(
                    icon: Icons.download_rounded,
                    onTap: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(
                            '长按图片可保存到相册',
                            style: GoogleFonts.inter(fontSize: 13),
                          ),
                          duration: const Duration(seconds: 2),
                          behavior: SnackBarBehavior.floating,
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
          ),

          // ── swipe hint ───────────────────────────────────────────────────
          const Positioned(
            bottom: 24,
            left: 0,
            right: 0,
            child: _SwipeHint(),
          ),
        ],
      ),
    );
  }
}

// ─── internal helpers ──────────────────────────────────────────────────────

class _CircleButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;

  const _CircleButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.all(8),
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: Colors.black.withValues(alpha: 0.45),
          shape: BoxShape.circle,
        ),
        child: Icon(icon, color: Colors.white, size: 20),
      ),
    );
  }
}

class _SwipeHint extends StatelessWidget {
  const _SwipeHint();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Text(
        '下滑关闭 · 双指缩放',
        style: GoogleFonts.inter(
          fontSize: 11,
          color: Colors.white.withValues(alpha: 0.4),
        ),
      ),
    );
  }
}
