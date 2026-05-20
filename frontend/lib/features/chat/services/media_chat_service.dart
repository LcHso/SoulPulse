// ============================================================================
// MediaChatService — multipart media upload for AI chat
// ============================================================================
//
// Sends image / voice / video files to the backend and receives an AI reply.
// Uses multipart/form-data so files of any size can be streamed.
// ============================================================================

import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import '../../../core/api/api_client.dart';

/// Result returned after a media message upload
class MediaChatResult {
  /// AI reply text
  final String? replyText;

  /// URL of the uploaded media (echoed back by the server)
  final String? mediaUrl;

  /// Media type: "image", "voice", "video"
  final String? mediaType;

  /// URL of an AI-generated voice reply (only when generateVoiceReply = true)
  final String? voiceUrl;

  /// Duration in seconds of a voice message
  final int? voiceDuration;

  /// Database ID of the newly created AI reply message
  final int? messageId;

  const MediaChatResult({
    this.replyText,
    this.mediaUrl,
    this.mediaType,
    this.voiceUrl,
    this.voiceDuration,
    this.messageId,
  });

  factory MediaChatResult.fromJson(Map<String, dynamic> json) {
    return MediaChatResult(
      replyText: json['reply'] as String?,
      mediaUrl: json['media_url'] as String?,
      mediaType: json['media_type'] as String?,
      voiceUrl: json['voice_url'] as String?,
      voiceDuration: json['voice_duration'] as int?,
      messageId: json['message_id'] as int?,
    );
  }
}

/// Service for uploading media files and receiving AI responses
class MediaChatService {
  /// Upload a media file and get an AI response.
  ///
  /// [personaId] — the AI persona's database ID
  /// [fileBytes] — raw bytes of the file
  /// [fileName]  — file name including extension (e.g. "photo.jpg")
  /// [mediaType] — one of: "image", "voice", "video"
  /// [caption]   — optional text caption / description
  /// [generateVoiceReply] — ask the AI to respond with a voice clip
  static Future<MediaChatResult> sendMedia({
    required int personaId,
    required Uint8List fileBytes,
    required String fileName,
    required String mediaType,
    String? caption,
    bool generateVoiceReply = false,
  }) async {
    final uri =
        Uri.parse('${ApiClient.baseUrl}/api/chat/$personaId/media');

    final request = http.MultipartRequest('POST', uri);

    // Auth header
    if (ApiClient.token != null) {
      request.headers['Authorization'] = 'Bearer ${ApiClient.token}';
    }

    // Attach the file
    request.files.add(
      http.MultipartFile.fromBytes(
        'file',
        fileBytes,
        filename: fileName,
      ),
    );

    // Form fields
    request.fields['media_type'] = mediaType;
    if (caption != null && caption.isNotEmpty) {
      request.fields['caption'] = caption;
    }
    if (generateVoiceReply) {
      request.fields['generate_voice_reply'] = 'true';
    }

    final streamed =
        await request.send().timeout(const Duration(seconds: 60));
    final response = await http.Response.fromStream(streamed);

    if (response.statusCode == 401) {
      ApiClient.onUnauthorized?.call();
      throw Exception('Unauthorized');
    }

    if (response.statusCode >= 400) {
      final Map<String, dynamic> err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Upload failed');
    }

    final raw = jsonDecode(response.body) as Map<String, dynamic>;

    // Rewrite any relative / localhost URLs in string fields
    final rewritten = raw.map((k, v) {
      if (v is String) return MapEntry(k, ApiClient.proxyImageUrl(v));
      return MapEntry(k, v);
    });

    return MediaChatResult.fromJson(rewritten);
  }
}
