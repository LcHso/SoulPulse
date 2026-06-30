// ============================================================================
// MediaAttachmentBar — row of media-picker buttons in the chat input area
// ============================================================================
//
// Provides Camera, Gallery, Microphone, and Video buttons.
// Uses image_picker for photo/video selection.
// Mic button delegates to the parent widget to toggle VoiceRecorder.
// ============================================================================

import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';
import '../../../core/theme/character_theme.dart';
import '../../../core/utils/image_compressor.dart';

/// Called when a media file has been selected and is ready to send.
/// [bytes]     — raw bytes of the file
/// [fileName]  — original file name (used when uploading)
/// [mediaType] — one of "image", "video"
typedef MediaSelectedCallback = void Function(
  Uint8List bytes,
  String fileName,
  String mediaType,
);

/// Compact horizontal bar of media-attachment icon buttons.
///
/// Sits directly above (or below) the text input row. Each icon opens a
/// platform picker or triggers the voice-recorder mode in the parent.
class MediaAttachmentBar extends StatelessWidget {
  /// Fired after a photo or video is successfully picked / captured.
  final MediaSelectedCallback onMediaSelected;

  /// Fired when the user taps the microphone button; the parent decides
  /// whether to show or hide the [VoiceRecorder].
  final VoidCallback onMicTapped;

  /// Whether the bar buttons are interactive (false while a send is in flight).
  final bool enabled;

  /// Character palette used to tint the icons.
  final CharacterColors characterColors;

  const MediaAttachmentBar({
    super.key,
    required this.onMediaSelected,
    required this.onMicTapped,
    required this.characterColors,
    this.enabled = true,
  });

  // ─── pickers ──────────────────────────────────────────────────────────────

  Future<void> _capturePhoto(BuildContext context) async {
    try {
      final file = await ImagePicker().pickImage(
        source: ImageSource.camera,
      );
      if (file == null) return;
      final rawBytes = await file.readAsBytes();
      // Compress before upload: max 1920px, 80% JPEG quality
      final compressed = await ImageCompressor.compress(rawBytes);
      final bytes = compressed ?? rawBytes;
      final fileName = _jpegFileName(file.name);
      onMediaSelected(bytes, fileName, 'image');
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Cannot open camera: $e')),
        );
      }
    }
  }

  Future<void> _pickFromGallery(BuildContext context) async {
    try {
      final file = await ImagePicker().pickImage(
        source: ImageSource.gallery,
      );
      if (file == null) return;
      final rawBytes = await file.readAsBytes();
      // Compress before upload: max 1920px, 80% JPEG quality
      final compressed = await ImageCompressor.compress(rawBytes);
      final bytes = compressed ?? rawBytes;
      final fileName = _jpegFileName(file.name);
      onMediaSelected(bytes, fileName, 'image');
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Cannot open gallery: $e')),
        );
      }
    }
  }

  Future<void> _pickVideo(BuildContext context) async {
    try {
      final file = await ImagePicker().pickVideo(
        source: ImageSource.gallery,
        maxDuration: const Duration(seconds: 60),
      );
      if (file == null) return;
      final bytes = await file.readAsBytes();
      onMediaSelected(bytes, file.name, 'video');
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Cannot pick video: $e')),
        );
      }
    }
  }

  /// Replace file extension with .jpg since we always re-encode as JPEG.
  static String _jpegFileName(String original) {
    final dotIdx = original.lastIndexOf('.');
    if (dotIdx > 0) {
      return '${original.substring(0, dotIdx)}.jpg';
    }
    return '$original.jpg';
  }

  // ─── build ────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final baseColor =
        enabled ? characterColors.primary : Colors.grey.shade400;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _AttachButton(
            icon: Icons.camera_alt_outlined,
            label: '拍照',
            color: baseColor,
            enabled: enabled,
            onTap: () => _capturePhoto(context),
          ),
          _AttachButton(
            icon: Icons.photo_library_outlined,
            label: '相册',
            color: baseColor,
            enabled: enabled,
            onTap: () => _pickFromGallery(context),
          ),
          _AttachButton(
            icon: Icons.mic_none_rounded,
            label: '语音',
            color: baseColor,
            enabled: enabled,
            onTap: onMicTapped,
          ),
          _AttachButton(
            icon: Icons.videocam_outlined,
            label: '视频',
            color: baseColor,
            enabled: enabled,
            onTap: () => _pickVideo(context),
          ),
        ],
      ),
    );
  }
}

// ─── internal icon button ──────────────────────────────────────────────────

class _AttachButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final bool enabled;
  final VoidCallback onTap;

  const _AttachButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.enabled,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: label,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: enabled ? onTap : null,
          borderRadius: BorderRadius.circular(20),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
            child: Icon(icon, size: 22, color: color),
          ),
        ),
      ),
    );
  }
}

// ─── upload preview overlay ────────────────────────────────────────────────

/// Small inline chip shown while a media file is queued for sending.
///
/// Displays a thumbnail (for images) or a file-type icon, plus a dismiss ×.
class MediaPreviewChip extends StatelessWidget {
  /// Raw bytes of the selected file (used for image preview).
  final Uint8List bytes;

  /// Media type: "image", "video", "voice".
  final String mediaType;

  /// Called when the user taps the × to remove the pending attachment.
  final VoidCallback onRemove;

  const MediaPreviewChip({
    super.key,
    required this.bytes,
    required this.mediaType,
    required this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6, left: 4, right: 4),
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color:
              Theme.of(context).colorScheme.outline.withValues(alpha: 0.3),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Thumbnail or icon
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: mediaType == 'image'
                ? Image.memory(
                    bytes,
                    width: 48,
                    height: 48,
                    fit: BoxFit.cover,
                  )
                : Container(
                    width: 48,
                    height: 48,
                    color:
                        Theme.of(context).colorScheme.surfaceContainerHighest,
                    child: Icon(
                      mediaType == 'video'
                          ? Icons.videocam
                          : Icons.audio_file,
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
          ),
          const SizedBox(width: 6),
          // Label
          Text(
            mediaType == 'image'
                ? 'Photo'
                : mediaType == 'video'
                    ? 'Video'
                    : 'Voice',
            style: GoogleFonts.inter(fontSize: 12),
          ),
          const SizedBox(width: 4),
          // Remove button
          GestureDetector(
            onTap: onRemove,
            child: Icon(
              Icons.close,
              size: 16,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}
