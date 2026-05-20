// ============================================================================
// VoiceRecorder — hold-to-record voice message widget
// ============================================================================
//
// Features:
//  • Hold the mic button to start recording; release to send.
//  • Slide up while holding to cancel.
//  • Pulse animation on the button during recording.
//  • Real-time waveform bars driven by microphone amplitude.
//  • Duration counter (MM:SS).
//  • Cross-platform: uses record's startStream() API — no dart:io required.
// ============================================================================

import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:record/record.dart';
import '../../../core/theme/character_theme.dart';

/// Called when a voice recording has been completed.
///
/// [bytes]    — concatenated audio bytes from the recording stream.
/// [fileName] — suggested file name (e.g. "voice_message.webm").
/// [duration] — recording length in whole seconds.
typedef VoiceRecordedCallback = void Function(
  Uint8List bytes,
  String fileName,
  int duration,
);

/// Widget that lets users hold-to-record a voice message.
///
/// Place this inside the chat input area. It is only visible when the user
/// taps the microphone button in [MediaAttachmentBar].
class VoiceRecorder extends StatefulWidget {
  /// Fired with the completed audio when the user releases the button.
  final VoiceRecordedCallback onRecorded;

  /// Fired when the user slides up to cancel or taps the × button.
  final VoidCallback onCancelled;

  /// Character palette used for theming.
  final CharacterColors characterColors;

  const VoiceRecorder({
    super.key,
    required this.onRecorded,
    required this.onCancelled,
    required this.characterColors,
  });

  @override
  State<VoiceRecorder> createState() => _VoiceRecorderState();
}

class _VoiceRecorderState extends State<VoiceRecorder>
    with TickerProviderStateMixin {
  // ─── recorder ─────────────────────────────────────────────────────────────
  final AudioRecorder _recorder = AudioRecorder();
  StreamSubscription<Uint8List>? _streamSub;
  final List<Uint8List> _audioChunks = [];

  // ─── state ─────────────────────────────────────────────────────────────────
  bool _isRecording = false;
  int _seconds = 0;
  Timer? _durationTimer;
  Timer? _amplitudeTimer;

  // Waveform bars — 20 values between 0 and 1
  final List<double> _bars = List.filled(20, 0.15);

  // Drag detection: sliding upward past threshold cancels recording
  double _cumulativeOffsetY = 0;
  static const double _cancelThreshold = -55.0;

  // ─── animations ───────────────────────────────────────────────────────────
  late final AnimationController _pulseCtrl;
  late final Animation<double> _pulseAnim;

  // ─── lifecycle ────────────────────────────────────────────────────────────

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );
    _pulseAnim = Tween<double>(begin: 1.0, end: 1.18).animate(
      CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _durationTimer?.cancel();
    _amplitudeTimer?.cancel();
    _streamSub?.cancel();
    _pulseCtrl.dispose();
    _recorder.dispose();
    super.dispose();
  }

  // ─── recording control ────────────────────────────────────────────────────

  Future<void> _startRecording() async {
    if (_isRecording) return;
    try {
      final hasPermission = await _recorder.hasPermission();
      if (!hasPermission) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('需要麦克风权限才能录音')),
          );
        }
        return;
      }

      _audioChunks.clear();

      // Stream audio — works on web (webm/opus) and mobile (AAC)
      final stream = await _recorder.startStream(
        const RecordConfig(
          encoder: AudioEncoder.aacLc,
          sampleRate: 16000,
          numChannels: 1,
          bitRate: 32000,
        ),
      );

      _streamSub = stream.listen((chunk) {
        _audioChunks.add(chunk);
      });

      setState(() {
        _isRecording = true;
        _seconds = 0;
        _cumulativeOffsetY = 0;
      });

      _pulseCtrl.repeat(reverse: true);

      // Duration counter — tick every second
      _durationTimer =
          Timer.periodic(const Duration(seconds: 1), (_) {
        if (!mounted) return;
        setState(() {
          _seconds++;
          // Cap at 2 minutes
          if (_seconds >= 120) _stopRecording();
        });
      });

      // Amplitude poller — update waveform bars ~10 times/sec
      _amplitudeTimer =
          Timer.periodic(const Duration(milliseconds: 100), (_) async {
        if (!_isRecording || !mounted) return;
        try {
          final amp = await _recorder.getAmplitude();
          // amp.current is dBFS (typically -160 to 0); map to 0–1
          final normalized = ((amp.current + 80.0) / 80.0).clamp(0.0, 1.0);
          if (mounted) {
            setState(() {
              _bars.removeAt(0);
              _bars.add(normalized.toDouble());
            });
          }
        } catch (_) {
          // Permission denied or recorder not active — ignore
        }
      });
    } catch (e) {
      if (mounted) setState(() => _isRecording = false);
    }
  }

  Future<void> _stopRecording({bool cancel = false}) async {
    if (!_isRecording) return;
    _durationTimer?.cancel();
    _amplitudeTimer?.cancel();
    _pulseCtrl.stop();
    _pulseCtrl.reset();

    try {
      await _streamSub?.cancel();
      _streamSub = null;
      await _recorder.stop();
    } catch (_) {}

    final duration = _seconds;
    final chunks = List<Uint8List>.from(_audioChunks);

    setState(() {
      _isRecording = false;
      _seconds = 0;
      for (int i = 0; i < _bars.length; i++) {
        _bars[i] = 0.15;
      }
    });

    if (cancel || _willCancel) {
      widget.onCancelled();
      return;
    }

    if (chunks.isEmpty) {
      widget.onCancelled();
      return;
    }

    // Concatenate all stream chunks into a single byte array
    final totalLength = chunks.fold<int>(0, (sum, c) => sum + c.length);
    final allBytes = Uint8List(totalLength);
    var offset = 0;
    for (final chunk in chunks) {
      allBytes.setAll(offset, chunk);
      offset += chunk.length;
    }

    widget.onRecorded(allBytes, 'voice_message.m4a', duration);
  }

  // ─── helpers ──────────────────────────────────────────────────────────────

  bool get _willCancel => _cumulativeOffsetY < _cancelThreshold;

  String get _durationText {
    final m = _seconds ~/ 60;
    final s = _seconds % 60;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  // ─── build ────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = widget.characterColors.primary;
    final cancelColor = _willCancel ? Colors.redAccent : Colors.grey.shade500;

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border(
          top: BorderSide(
            color: theme.colorScheme.outline.withValues(alpha: 0.15),
          ),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // ── slide-up-to-cancel hint ──────────────────────────────────────
          AnimatedOpacity(
            opacity: _isRecording ? 1.0 : 0.0,
            duration: const Duration(milliseconds: 200),
            child: Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.arrow_upward_rounded,
                      size: 13, color: cancelColor),
                  const SizedBox(width: 4),
                  Text(
                    _willCancel ? '松开取消' : '上滑取消',
                    style: GoogleFonts.inter(
                        fontSize: 12, color: cancelColor),
                  ),
                ],
              ),
            ),
          ),

          // ── waveform bars ────────────────────────────────────────────────
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 150),
            child: _isRecording
                ? SizedBox(
                    key: const ValueKey('wave'),
                    height: 36,
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        for (int i = 0; i < _bars.length; i++)
                          AnimatedContainer(
                            duration: const Duration(milliseconds: 80),
                            margin:
                                const EdgeInsets.symmetric(horizontal: 1.5),
                            width: 3,
                            height: 4 + _bars[i] * 28,
                            decoration: BoxDecoration(
                              color: color.withValues(
                                  alpha: 0.45 + _bars[i] * 0.55),
                              borderRadius: BorderRadius.circular(2),
                            ),
                          ),
                      ],
                    ),
                  )
                : const SizedBox(key: ValueKey('empty'), height: 36),
          ),

          const SizedBox(height: 6),

          // ── duration + mic button row ────────────────────────────────────
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Duration counter (only when recording)
              SizedBox(
                width: 64,
                child: _isRecording
                    ? Row(
                        children: [
                          // Blinking red dot
                          _BlinkDot(color: Colors.redAccent),
                          const SizedBox(width: 4),
                          Text(
                            _durationText,
                            style: GoogleFonts.inter(
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                              color: theme.colorScheme.onSurface,
                            ),
                          ),
                        ],
                      )
                    : const SizedBox.shrink(),
              ),

              // Mic button
              GestureDetector(
                onLongPressStart: (_) => _startRecording(),
                onLongPressEnd: (_) => _stopRecording(),
                onLongPressCancel: () => _stopRecording(cancel: true),
                onVerticalDragUpdate: (d) {
                  if (!_isRecording) return;
                  setState(() => _cumulativeOffsetY += d.delta.dy);
                },
                onVerticalDragEnd: (_) {
                  if (_isRecording) {
                    _stopRecording(cancel: _willCancel);
                  }
                },
                child: AnimatedBuilder(
                  animation: _pulseAnim,
                  builder: (_, child) => Transform.scale(
                    scale: _isRecording ? _pulseAnim.value : 1.0,
                    child: child,
                  ),
                  child: Container(
                    width: 62,
                    height: 62,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: _isRecording
                          ? (_willCancel
                              ? Colors.redAccent
                              : color)
                          : color.withValues(alpha: 0.12),
                      border: Border.all(
                        color:
                            _isRecording ? Colors.transparent : color,
                        width: 2,
                      ),
                      boxShadow: _isRecording
                          ? [
                              BoxShadow(
                                color: (_willCancel ? Colors.redAccent : color)
                                    .withValues(alpha: 0.45),
                                blurRadius: 18,
                                spreadRadius: 4,
                              )
                            ]
                          : [],
                    ),
                    child: Icon(
                      _isRecording
                          ? Icons.mic_rounded
                          : Icons.mic_none_rounded,
                      color: _isRecording ? Colors.white : color,
                      size: 28,
                    ),
                  ),
                ),
              ),

              // Trailing space to balance the duration counter
              const SizedBox(width: 64),
            ],
          ),

          const SizedBox(height: 4),

          // ── instruction / cancel button ───────────────────────────────────
          if (!_isRecording) ...[
            Text(
              '长按录音',
              style: GoogleFonts.inter(
                fontSize: 12,
                color: Colors.grey.shade500,
              ),
            ),
            const SizedBox(height: 2),
            TextButton(
              onPressed: widget.onCancelled,
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(
                    horizontal: 12, vertical: 4),
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: Text(
                '关闭',
                style: GoogleFonts.inter(
                    fontSize: 12, color: Colors.grey.shade500),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

// ─── blinking red dot ──────────────────────────────────────────────────────

class _BlinkDot extends StatefulWidget {
  final Color color;
  const _BlinkDot({required this.color});

  @override
  State<_BlinkDot> createState() => _BlinkDotState();
}

class _BlinkDotState extends State<_BlinkDot>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, __) => Container(
        width: 7,
        height: 7,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: widget.color.withValues(alpha: 0.4 + _ctrl.value * 0.6),
        ),
      ),
    );
  }
}
