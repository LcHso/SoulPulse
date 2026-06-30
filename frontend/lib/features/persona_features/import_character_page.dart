// ============================================================================
// SoulPulse - Character Card Import Page
// Lets users import SillyTavern V2 character cards (PNG with embedded JSON,
// or raw JSON) and turn them into private AI personas. Flow: pick file ->
// /character-cards/import (preview) -> /character-cards/import-and-create ->
// open chat with the new persona.
// ============================================================================

import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api/api_client.dart';

const String _kImportPreviewPath = '/character-cards/import';
const String _kImportCreatePath = '/character-cards/import-and-create';
const int _kMaxFileSizeBytes = 10 * 1024 * 1024; // 10MB (mirrors backend)

/// Page that walks a user through importing a SillyTavern character card.
class ImportCharacterPage extends StatefulWidget {
  const ImportCharacterPage({super.key});

  @override
  State<ImportCharacterPage> createState() => _ImportCharacterPageState();
}

class _ImportCharacterPageState extends State<ImportCharacterPage> {
  // ── Selected file state ────────────────────────────────────────────
  Uint8List? _fileBytes;
  String? _fileName;
  String? _fileExtension; // 'png' or 'json'

  // ── Parsed-preview state ────────────────────────────────────────────
  Map<String, dynamic>? _personaData;
  Map<String, dynamic>? _cardData;

  // ── UI state flags ────────────────────────────────────────────────
  bool _isParsing = false;
  bool _isCreating = false;
  String? _errorMessage;

  // ── Quota state ──────────────────────────────────────────────────
  int? _quotaUsed;
  int? _quotaLimit; // null means unlimited (subscriber)
  bool _isSubscriber = false;
  bool _quotaLoaded = false;

  final TextEditingController _nameOverrideCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadQuota();
  }

  @override
  void dispose() {
    _nameOverrideCtrl.dispose();
    super.dispose();
  }

  /// Load quota info on page init for the info banner.
  Future<void> _loadQuota() async {
    try {
      final quota = await ApiClient.get('/character-cards/import-quota');
      if (!mounted) return;
      setState(() {
        _quotaUsed = (quota['used'] as num?)?.toInt() ?? 0;
        final limitRaw = quota['limit'];
        _quotaLimit = limitRaw is num ? limitRaw.toInt() : null;
        _isSubscriber = quota['is_subscriber'] == true;
        _quotaLoaded = true;
      });
    } catch (_) {
      // Silently fail — the backend still enforces limits.
    }
  }

  /// Check quota before allowing file selection. Returns true if import is allowed.
  Future<bool> _checkQuota() async {
    try {
      final quota = await ApiClient.get('/character-cards/import-quota');
      final used = (quota['used'] as num?)?.toInt() ?? 0;
      final limitRaw = quota['limit'];
      final limit = limitRaw is num ? limitRaw.toInt() : null;
      final isSubscriber = quota['is_subscriber'] == true;

      // Update local state so the banner stays fresh
      if (mounted) {
        setState(() {
          _quotaUsed = used;
          _quotaLimit = limit;
          _isSubscriber = isSubscriber;
          _quotaLoaded = true;
        });
      }

      if (!isSubscriber && limit != null && used >= limit) {
        if (mounted) {
          showDialog(
            context: context,
            builder: (ctx) => AlertDialog(
              title: const Text('导入上限已达'),
              content: Text('免费用户最多可导入 $limit 个角色。\n订阅解锁无限导入。'),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text('我知道了'),
                ),
                FilledButton(
                  onPressed: () {
                    Navigator.pop(ctx);
                    context.push('/subscription');
                  },
                  child: const Text('去订阅'),
                ),
              ],
            ),
          );
        }
        return false;
      }
      return true;
    } catch (_) {
      // If quota check fails, allow the import to proceed
      // (the backend will enforce the limit anyway)
      return true;
    }
  }

  // ──────────────────────────────────────────────────────────────────
  //   File selection + preview
  // ──────────────────────────────────────────────────────────────────

  /// Open the file picker (PNG / JSON), then call the backend's parse-only
  /// endpoint to populate a preview.
  Future<void> _pickAndPreview() async {
    if (_isParsing || _isCreating) return;

    // Check quota before opening the file picker
    final canImport = await _checkQuota();
    if (!canImport) return;

    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: const ['png', 'json'],
        withData: true, // we need bytes for both web & native uploads
      );
      if (result == null || result.files.isEmpty) return;

      final picked = result.files.single;
      final bytes = picked.bytes;
      if (bytes == null) {
        _showError('Could not read the selected file.');
        return;
      }
      if (bytes.lengthInBytes > _kMaxFileSizeBytes) {
        _showError('File too large. Maximum allowed size is 10MB.');
        return;
      }

      final name = picked.name;
      final ext = (picked.extension ?? _extFromName(name)).toLowerCase();
      if (ext != 'png' && ext != 'json') {
        _showError('Unsupported file type. Only .png and .json are accepted.');
        return;
      }

      setState(() {
        _fileBytes = bytes;
        _fileName = name;
        _fileExtension = ext;
        _personaData = null;
        _cardData = null;
        _errorMessage = null;
        _isParsing = true;
      });

      final response = await ApiClient.postMultipart(
        _kImportPreviewPath,
        fileBytes: bytes,
        fileName: name,
      );

      if (!mounted) return;
      setState(() {
        _personaData =
            (response['persona_data'] as Map?)?.cast<String, dynamic>();
        _cardData = (response['card'] as Map?)?.cast<String, dynamic>();
        _isParsing = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isParsing = false;
        _errorMessage = _stripException(e);
      });
      _showError(_errorMessage!);
    }
  }

  /// Send the same file bytes (plus optional name override) to the
  /// import-and-create endpoint, which provisions a private persona.
  Future<void> _importAndCreate() async {
    if (_fileBytes == null || _fileName == null) return;
    if (_isCreating || _isParsing) return;

    setState(() {
      _isCreating = true;
      _errorMessage = null;
    });

    try {
      final fields = <String, String>{};
      final override = _nameOverrideCtrl.text.trim();
      if (override.isNotEmpty) {
        fields['name_override'] = override;
      }

      final response = await ApiClient.postMultipart(
        _kImportCreatePath,
        fileBytes: _fileBytes!,
        fileName: _fileName!,
        fields: fields,
      );

      if (!mounted) return;
      // Invalidate cached persona lists so the new character appears on
      // Discover / Chats immediately.
      ApiClient.invalidateCache('/api/ai/personas');

      final persona = (response['persona'] as Map?)?.cast<String, dynamic>();
      final personaId = persona?['id'] as int?;
      final personaName = (persona?['name'] as String?)?.trim().isNotEmpty == true
          ? persona!['name'] as String
          : (_personaData?['name'] as String? ?? 'New Companion');

      _showSuccess('Character imported successfully!');
      // Capture the router up front: after we pop the import page the local
      // context will be detached from the tree.
      final router = GoRouter.of(context);
      if (personaId != null) {
        router.pop();
        router.push(
          '/chat/$personaId?name=${Uri.encodeComponent(personaName)}',
        );
      } else {
        router.pop();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isCreating = false;
        _errorMessage = _stripException(e);
      });
      _showError(_errorMessage!);
    }
  }

  void _resetSelection() {
    setState(() {
      _fileBytes = null;
      _fileName = null;
      _fileExtension = null;
      _personaData = null;
      _cardData = null;
      _errorMessage = null;
      _nameOverrideCtrl.clear();
    });
  }

  // ──────────────────────────────────────────────────────────────────
  //   Helpers
  // ──────────────────────────────────────────────────────────────────

  String _extFromName(String fileName) {
    final dot = fileName.lastIndexOf('.');
    if (dot < 0 || dot == fileName.length - 1) return '';
    return fileName.substring(dot + 1);
  }

  String _stripException(Object e) {
    final text = e.toString();
    const prefix = 'Exception: ';
    return text.startsWith(prefix) ? text.substring(prefix.length) : text;
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          behavior: SnackBarBehavior.floating,
          backgroundColor: const Color(0xFF8E2A3C),
          content: Text(
            message,
            style: GoogleFonts.inter(color: Colors.white),
          ),
        ),
      );
  }

  void _showSuccess(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          behavior: SnackBarBehavior.floating,
          backgroundColor: const Color(0xFF4F6B5A),
          content: Text(
            message,
            style: GoogleFonts.inter(color: Colors.white),
          ),
        ),
      );
  }

  // ──────────────────────────────────────────────────────────────────
  //   Build
  // ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final hasPreview = _personaData != null;

    return Scaffold(
      backgroundColor: isDark ? const Color(0xFF161228) : const Color(0xFFFAF6F3),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Text(
          'Import Character',
          style: GoogleFonts.inter(
            fontWeight: FontWeight.w700,
            fontSize: 20,
            letterSpacing: -0.2,
          ),
        ),
      ),
      body: Stack(
        children: [
          // Soft ambient gradient backdrop for the "summoning" mood.
          Positioned.fill(
            child: IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    center: const Alignment(-0.6, -0.7),
                    radius: 1.1,
                    colors: isDark
                        ? const [Color(0x33B58CCC), Color(0x00161228)]
                        : const [Color(0x33E6A4B4), Color(0x00FAF6F3)],
                  ),
                ),
              ),
            ),
          ),
          SafeArea(
            top: false,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 520),
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 120),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _buildIntro(theme, isDark),
                      const SizedBox(height: 12),
                      _buildQuotaInfo(isDark),
                      const SizedBox(height: 16),
                      AnimatedSwitcher(
                        duration: const Duration(milliseconds: 280),
                        switchInCurve: Curves.easeOutCubic,
                        switchOutCurve: Curves.easeInCubic,
                        transitionBuilder: (child, anim) => FadeTransition(
                          opacity: anim,
                          child: SlideTransition(
                            position: Tween<Offset>(
                              begin: const Offset(0, 0.04),
                              end: Offset.zero,
                            ).animate(anim),
                            child: child,
                          ),
                        ),
                        child: hasPreview
                            ? _buildPreviewCard(
                                key: const ValueKey('preview'),
                                theme: theme,
                                isDark: isDark,
                              )
                            : _buildDropZone(
                                key: const ValueKey('dropzone'),
                                theme: theme,
                                isDark: isDark,
                              ),
                      ),
                      if (hasPreview) ...[
                        const SizedBox(height: 18),
                        _buildNameOverrideField(theme, isDark),
                        const SizedBox(height: 12),
                        _buildSecondaryActions(theme, isDark),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
          // Sticky CTA at the bottom — only meaningful once we have a preview.
          if (hasPreview)
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: _buildStickyImportBar(theme, isDark),
            ),
        ],
      ),
    );
  }

  // ── Quota info banner ─────────────────────────────────────────────
  Widget _buildQuotaInfo(bool isDark) {
    if (!_quotaLoaded) return const SizedBox.shrink();

    final accent = isDark ? const Color(0xFFE6A4B4) : const Color(0xFFB47B84);
    final muted = isDark ? const Color(0xFFA095AC) : const Color(0xFF7A6A78);

    if (_isSubscriber) {
      return Row(
        children: [
          Icon(Icons.workspace_premium, size: 16, color: accent),
          const SizedBox(width: 6),
          Text(
            '订阅用户 · 无限导入',
            style: GoogleFonts.inter(
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
              color: accent,
            ),
          ),
        ],
      );
    }

    final limit = _quotaLimit ?? 3;
    final used = _quotaUsed ?? 0;
    final atLimit = used >= limit;

    return Row(
      children: [
        Icon(
          atLimit ? Icons.warning_amber_rounded : Icons.inventory_2_outlined,
          size: 16,
          color: atLimit ? Colors.redAccent[200] : muted,
        ),
        const SizedBox(width: 6),
        Text(
          '免费额度: $used/$limit',
          style: GoogleFonts.inter(
            fontSize: 12.5,
            fontWeight: FontWeight.w600,
            color: atLimit ? Colors.redAccent[200] : muted,
          ),
        ),
        if (atLimit) ...[
          const SizedBox(width: 8),
          Text(
            '已满',
            style: GoogleFonts.inter(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: Colors.redAccent[200],
            ),
          ),
        ],
      ],
    );
  }

  // ── Intro / header copy ────────────────────────────────────────────
  Widget _buildIntro(ThemeData theme, bool isDark) {
    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 4, left: 4, right: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Bring a companion home',
            style: GoogleFonts.inter(
              fontSize: 26,
              fontWeight: FontWeight.w800,
              height: 1.15,
              letterSpacing: -0.5,
              color: isDark ? Colors.white : const Color(0xFF221A2B),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Import a SillyTavern V2 character card (PNG or JSON). '
            'They\'ll appear in your private collection — only you can chat with them.',
            style: GoogleFonts.inter(
              fontSize: 13.5,
              height: 1.45,
              color: isDark ? const Color(0xFFB6ABC0) : const Color(0xFF6E5F70),
            ),
          ),
        ],
      ),
    );
  }

  // ── Empty / drop-zone state ────────────────────────────────────────
  Widget _buildDropZone({
    required Key key,
    required ThemeData theme,
    required bool isDark,
  }) {
    final accent = isDark ? const Color(0xFFE6A4B4) : const Color(0xFFB47B84);
    final border = isDark ? const Color(0x66E6A4B4) : const Color(0x80B47B84);
    final surface = isDark ? const Color(0xFF221B36) : Colors.white;

    return Container(
      key: key,
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(22),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(isDark ? 0.32 : 0.06),
            blurRadius: 22,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: _isParsing ? null : _pickAndPreview,
          borderRadius: BorderRadius.circular(22),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 24),
            child: Column(
              children: [
                // Custom dashed-border avatar slot to make the empty state feel
                // intentional rather than a generic placeholder.
                _DashedCircle(
                  size: 96,
                  color: border,
                  child: Center(
                    child: Icon(
                      Icons.auto_awesome_outlined,
                      size: 36,
                      color: accent,
                    ),
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                  _isParsing ? 'Reading your card…' : 'Tap to choose a card',
                  style: GoogleFonts.inter(
                    fontWeight: FontWeight.w700,
                    fontSize: 16,
                    color: isDark ? Colors.white : const Color(0xFF2A1F32),
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  _fileName ??
                      'Supported formats: .png (Tavern card) · .json (V2 card)',
                  textAlign: TextAlign.center,
                  style: GoogleFonts.inter(
                    fontSize: 12.5,
                    height: 1.45,
                    color: isDark
                        ? const Color(0xFFA095AC)
                        : const Color(0xFF8B7986),
                  ),
                ),
                if (_isParsing) ...[
                  const SizedBox(height: 18),
                  SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.4,
                      color: accent,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  // ── Preview card (parsed) ──────────────────────────────────────────
  Widget _buildPreviewCard({
    required Key key,
    required ThemeData theme,
    required bool isDark,
  }) {
    final data = _personaData!;
    final card = _cardData ?? const <String, dynamic>{};
    final dataSection = (card['data'] as Map?)?.cast<String, dynamic>() ?? card;

    final name = (data['name'] as String?)?.trim().isNotEmpty == true
        ? data['name'] as String
        : 'Unnamed Character';
    final bio = (data['bio'] as String?) ?? '';
    final personality = (dataSection['personality'] as String?) ?? '';
    final scenario = (data['family_background'] as String?) ?? '';
    final firstMes = (dataSection['first_mes'] as String?) ?? '';
    final creator = (dataSection['creator'] as String?) ?? '';
    final tags = (dataSection['tags'] is List)
        ? (dataSection['tags'] as List).whereType<String>().toList()
        : <String>[];

    final accent = isDark ? const Color(0xFFE6A4B4) : const Color(0xFFB47B84);
    final surface = isDark ? const Color(0xFF221B36) : Colors.white;
    final muted =
        isDark ? const Color(0xFFA095AC) : const Color(0xFF7A6A78);
    final foreground =
        isDark ? Colors.white : const Color(0xFF221A2B);

    return Container(
      key: key,
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(22),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(isDark ? 0.34 : 0.07),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 22, 20, 22),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _AvatarPreview(
                  bytes: _fileExtension == 'png' ? _fileBytes : null,
                  fallbackInitial: name.isNotEmpty ? name[0] : '?',
                  accent: accent,
                  isDark: isDark,
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        style: GoogleFonts.inter(
                          fontSize: 22,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.3,
                          color: foreground,
                        ),
                      ),
                      if (creator.isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Text(
                          'by $creator',
                          style: GoogleFonts.inter(
                            fontSize: 12.5,
                            color: muted,
                          ),
                        ),
                      ],
                      if (tags.isNotEmpty) ...[
                        const SizedBox(height: 10),
                        Wrap(
                          spacing: 6,
                          runSpacing: 6,
                          children: tags
                              .take(4)
                              .map((t) => _Pill(text: t, accent: accent, isDark: isDark))
                              .toList(),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 22),
            if (bio.trim().isNotEmpty)
              _PreviewSection(
                label: 'Description',
                body: bio.trim(),
                accent: accent,
                muted: muted,
                foreground: foreground,
              ),
            if (personality.trim().isNotEmpty) ...[
              const SizedBox(height: 14),
              _PreviewSection(
                label: 'Personality',
                body: personality.trim(),
                accent: accent,
                muted: muted,
                foreground: foreground,
                maxLines: 6,
              ),
            ],
            if (scenario.trim().isNotEmpty) ...[
              const SizedBox(height: 14),
              _PreviewSection(
                label: 'Scenario',
                body: scenario.trim(),
                accent: accent,
                muted: muted,
                foreground: foreground,
                maxLines: 4,
              ),
            ],
            if (firstMes.trim().isNotEmpty) ...[
              const SizedBox(height: 14),
              _PreviewSection(
                label: 'First message',
                body: firstMes.trim(),
                accent: accent,
                muted: muted,
                foreground: foreground,
                maxLines: 5,
                italic: true,
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildNameOverrideField(ThemeData theme, bool isDark) {
    return TextField(
      controller: _nameOverrideCtrl,
      enabled: !_isCreating,
      style: GoogleFonts.inter(
        fontSize: 14,
        color: isDark ? Colors.white : const Color(0xFF221A2B),
      ),
      decoration: InputDecoration(
        labelText: 'Custom name (optional)',
        labelStyle: GoogleFonts.inter(
          fontSize: 13,
          color: isDark
              ? const Color(0xFFA095AC)
              : const Color(0xFF7A6A78),
        ),
        hintText: 'Use a different name in your collection',
        hintStyle: GoogleFonts.inter(
          fontSize: 13,
          color: isDark
              ? const Color(0xFF695C72)
              : const Color(0xFFB1A4AC),
        ),
        filled: true,
        fillColor: isDark ? const Color(0xFF1E1830) : Colors.white,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(
            color: isDark
                ? const Color(0xFF3A2F4B)
                : const Color(0xFFEADBE0),
          ),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(
            color: isDark
                ? const Color(0xFF3A2F4B)
                : const Color(0xFFEADBE0),
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(
            color: isDark
                ? const Color(0xFFE6A4B4)
                : const Color(0xFFB47B84),
            width: 1.4,
          ),
        ),
      ),
    );
  }

  Widget _buildSecondaryActions(ThemeData theme, bool isDark) {
    return Row(
      children: [
        Expanded(
          child: TextButton.icon(
            onPressed: _isCreating ? null : _pickAndPreview,
            icon: const Icon(Icons.refresh_rounded, size: 18),
            label: Text(
              'Choose another file',
              style: GoogleFonts.inter(fontWeight: FontWeight.w600),
            ),
            style: TextButton.styleFrom(
              foregroundColor: isDark
                  ? const Color(0xFFE6A4B4)
                  : const Color(0xFFB47B84),
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: TextButton.icon(
            onPressed: _isCreating ? null : _resetSelection,
            icon: const Icon(Icons.close_rounded, size: 18),
            label: Text(
              'Discard',
              style: GoogleFonts.inter(fontWeight: FontWeight.w600),
            ),
            style: TextButton.styleFrom(
              foregroundColor: isDark
                  ? const Color(0xFFA095AC)
                  : const Color(0xFF7A6A78),
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildStickyImportBar(ThemeData theme, bool isDark) {
    final bg = isDark
        ? const Color(0xFF161228).withOpacity(0.92)
        : const Color(0xFFFAF6F3).withOpacity(0.96);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: bg,
        border: Border(
          top: BorderSide(
            color: isDark
                ? const Color(0xFF2A2240)
                : const Color(0xFFEADBE0),
            width: 1,
          ),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 14, 20, 16),
          child: SizedBox(
            height: 54,
            child: ElevatedButton(
              onPressed:
                  _isCreating || _personaData == null ? null : _importAndCreate,
              style: ElevatedButton.styleFrom(
                backgroundColor: isDark
                    ? const Color(0xFFE6A4B4)
                    : const Color(0xFFB47B84),
                foregroundColor: isDark
                    ? const Color(0xFF221A2B)
                    : Colors.white,
                disabledBackgroundColor: isDark
                    ? const Color(0xFF3A2F4B)
                    : const Color(0xFFE3D4D9),
                disabledForegroundColor: isDark
                    ? const Color(0xFF695C72)
                    : Colors.white70,
                elevation: 0,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                ),
              ),
              child: _isCreating
                  ? const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.4,
                        color: Colors.white,
                      ),
                    )
                  : Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.favorite_outline, size: 19),
                        const SizedBox(width: 10),
                        Text(
                          'Bring them in',
                          style: GoogleFonts.inter(
                            fontWeight: FontWeight.w700,
                            fontSize: 15,
                            letterSpacing: 0.2,
                          ),
                        ),
                      ],
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================================
//   Sub-widgets
// ============================================================================

/// Avatar bubble shown in the preview. PNG cards render their own bytes;
/// JSON cards fall back to the first letter on a tinted disc.
class _AvatarPreview extends StatelessWidget {
  final Uint8List? bytes;
  final String fallbackInitial;
  final Color accent;
  final bool isDark;

  const _AvatarPreview({
    required this.bytes,
    required this.fallbackInitial,
    required this.accent,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 84,
      height: 84,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: bytes == null
            ? LinearGradient(
                colors: [
                  accent.withOpacity(0.65),
                  accent.withOpacity(0.25),
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              )
            : null,
        boxShadow: [
          BoxShadow(
            color: accent.withOpacity(isDark ? 0.35 : 0.25),
            blurRadius: 18,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: ClipOval(
        child: bytes != null
            ? Image.memory(
                bytes!,
                fit: BoxFit.cover,
                gaplessPlayback: true,
                errorBuilder: (_, __, ___) => _initial(),
              )
            : _initial(),
      ),
    );
  }

  Widget _initial() => Center(
        child: Text(
          fallbackInitial.toUpperCase(),
          style: GoogleFonts.inter(
            fontSize: 32,
            fontWeight: FontWeight.w800,
            color: Colors.white,
          ),
        ),
      );
}

/// Labelled preview block showing one parsed field (description, personality,
/// scenario, first message…).
class _PreviewSection extends StatelessWidget {
  final String label;
  final String body;
  final Color accent;
  final Color muted;
  final Color foreground;
  final int maxLines;
  final bool italic;

  const _PreviewSection({
    required this.label,
    required this.body,
    required this.accent,
    required this.muted,
    required this.foreground,
    this.maxLines = 8,
    this.italic = false,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              width: 4,
              height: 14,
              decoration: BoxDecoration(
                color: accent,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              label.toUpperCase(),
              style: GoogleFonts.inter(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.4,
                color: muted,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          body,
          maxLines: maxLines,
          overflow: TextOverflow.ellipsis,
          style: GoogleFonts.inter(
            fontSize: 13.5,
            height: 1.55,
            color: foreground,
            fontStyle: italic ? FontStyle.italic : FontStyle.normal,
          ),
        ),
      ],
    );
  }
}

/// Small rounded chip used for tags.
class _Pill extends StatelessWidget {
  final String text;
  final Color accent;
  final bool isDark;

  const _Pill({required this.text, required this.accent, required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: accent.withOpacity(isDark ? 0.18 : 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: accent.withOpacity(0.35), width: 0.6),
      ),
      child: Text(
        text,
        style: GoogleFonts.inter(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: accent,
        ),
      ),
    );
  }
}

/// Decorative dashed circle used as the empty-state avatar slot.
class _DashedCircle extends StatelessWidget {
  final double size;
  final Color color;
  final Widget child;

  const _DashedCircle({
    required this.size,
    required this.color,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _DashedCirclePainter(color: color),
        child: child,
      ),
    );
  }
}

class _DashedCirclePainter extends CustomPainter {
  final Color color;
  _DashedCirclePainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;

    final center = size.center(Offset.zero);
    final radius = size.width / 2 - 1;

    // Draw 32 short dashes around the circumference.
    const dashCount = 32;
    const dashSweep = (3.14159 * 2) / dashCount * 0.55;
    final gap = (3.14159 * 2) / dashCount;
    for (int i = 0; i < dashCount; i++) {
      final start = i * gap;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        start,
        dashSweep,
        false,
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _DashedCirclePainter old) => old.color != color;
}
