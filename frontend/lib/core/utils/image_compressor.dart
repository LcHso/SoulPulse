// ============================================================================
// ImageCompressor — client-side image compression/resizing before upload
// ============================================================================
//
// Reduces bandwidth usage by 40-60% by resizing and re-encoding images as
// JPEG before upload. Uses the pure-Dart `image` package for full cross-
// platform support (Android, iOS, Web).
//
// Usage:
//   final compressed = await ImageCompressor.compress(rawBytes);
//   final avatar = await ImageCompressor.compressAvatar(rawBytes);
// ============================================================================

import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as img;

/// Client-side image compression utility.
///
/// Resizes images to a max dimension while preserving aspect ratio,
/// then re-encodes as JPEG at a specified quality level.
class ImageCompressor {
  ImageCompressor._();

  // ─── Public API ──────────────────────────────────────────────────────────

  /// Compress and resize an image for post/chat uploads.
  ///
  /// - Max dimension: [maxDimension] px (longest side, default 1920)
  /// - JPEG quality: [quality] (0–100, default 80)
  /// - Returns compressed JPEG bytes, or `null` if decoding fails.
  static Future<Uint8List?> compress(
    Uint8List bytes, {
    int maxDimension = 1920,
    int quality = 80,
  }) {
    return compute(
      _compressIsolate,
      _CompressParams(
        bytes: bytes,
        maxDimension: maxDimension,
        quality: quality,
      ),
    );
  }

  /// Compress and resize for avatar / profile images (smaller output).
  ///
  /// - Max dimension: [maxDimension] px (default 512)
  /// - JPEG quality: [quality] (default 85 — slightly higher for small images)
  static Future<Uint8List?> compressAvatar(
    Uint8List bytes, {
    int maxDimension = 512,
    int quality = 85,
  }) {
    return compress(bytes, maxDimension: maxDimension, quality: quality);
  }

  /// Compress for thumbnail generation.
  ///
  /// - Max dimension: [maxDimension] px (default 300)
  /// - JPEG quality: [quality] (default 75)
  static Future<Uint8List?> compressThumbnail(
    Uint8List bytes, {
    int maxDimension = 300,
    int quality = 75,
  }) {
    return compress(bytes, maxDimension: maxDimension, quality: quality);
  }

  // ─── Private implementation (runs in isolate via compute) ────────────────

  /// Top-level function suitable for [compute].
  static Uint8List? _compressIsolate(_CompressParams params) {
    // Decode the source image (supports JPEG, PNG, WebP, BMP, GIF, etc.)
    final decoded = img.decodeImage(params.bytes);
    if (decoded == null) return null;

    // Determine if resizing is needed
    img.Image resized;
    final longestSide =
        decoded.width > decoded.height ? decoded.width : decoded.height;

    if (longestSide > params.maxDimension) {
      // Resize preserving aspect ratio (interpolation: cubic for quality)
      if (decoded.width >= decoded.height) {
        resized = img.copyResize(
          decoded,
          width: params.maxDimension,
          interpolation: img.Interpolation.cubic,
        );
      } else {
        resized = img.copyResize(
          decoded,
          height: params.maxDimension,
          interpolation: img.Interpolation.cubic,
        );
      }
    } else {
      // No resize needed, but still re-encode to JPEG for consistent compression
      resized = decoded;
    }

    // Encode as JPEG
    final jpegBytes = img.encodeJpg(resized, quality: params.quality);
    return Uint8List.fromList(jpegBytes);
  }
}

/// Parameters passed to the isolate for compression.
class _CompressParams {
  final Uint8List bytes;
  final int maxDimension;
  final int quality;

  const _CompressParams({
    required this.bytes,
    required this.maxDimension,
    required this.quality,
  });
}
