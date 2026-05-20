/// Interactive choice cards widget for SoulPulse scenes.
///
/// Displayed when an AI response contains choices in the format:
/// [CHOICE_A: text | CHOICE_B: text | CHOICE_C: text]
///
/// Features:
/// - Staggered fade-in animation
/// - Tappable choice cards
/// - Disabled state after selection (shows which was picked)
/// - Sends choice to scene API

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Data model for a parsed choice option.
class SceneChoice {
  final String key;
  final String text;

  const SceneChoice({required this.key, required this.text});
}

/// Widget that displays interactive scene choices.
///
/// Usage:
/// ```dart
/// SceneChoiceCards(
///   choices: parseChoices(aiMessage),
///   selectedKey: null,
///   onChoiceSelected: (key) => handleChoice(key),
/// )
/// ```
class SceneChoiceCards extends StatefulWidget {
  /// List of available choices
  final List<SceneChoice> choices;

  /// Currently selected choice key (null if not yet selected)
  final String? selectedKey;

  /// Callback when user taps a choice
  final ValueChanged<String> onChoiceSelected;

  /// Whether interaction is disabled (e.g., sending choice to API)
  final bool disabled;

  const SceneChoiceCards({
    super.key,
    required this.choices,
    this.selectedKey,
    required this.onChoiceSelected,
    this.disabled = false,
  });

  /// Parse choice format from AI message text.
  ///
  /// Expected format: [CHOICE_A: text | CHOICE_B: text | CHOICE_C: text]
  /// Returns empty list if no choices found.
  static List<SceneChoice> parseChoices(String message) {
    final regex = RegExp(r'\[(.+?)\]');
    final match = regex.firstMatch(message);
    if (match == null) return [];

    final content = match.group(1)!;
    final parts = content.split('|');

    final choices = <SceneChoice>[];
    for (final part in parts) {
      final trimmed = part.trim();
      final colonIndex = trimmed.indexOf(':');
      if (colonIndex == -1) continue;

      final key = trimmed.substring(0, colonIndex).trim();
      final text = trimmed.substring(colonIndex + 1).trim();

      if (key.isNotEmpty && text.isNotEmpty) {
        choices.add(SceneChoice(key: key, text: text));
      }
    }

    return choices;
  }

  /// Remove choice markup from message text for display.
  static String stripChoiceMarkup(String message) {
    return message.replaceAll(RegExp(r'\[.+?\]'), '').trim();
  }

  @override
  State<SceneChoiceCards> createState() => _SceneChoiceCardsState();
}

class _SceneChoiceCardsState extends State<SceneChoiceCards>
    with TickerProviderStateMixin {
  late List<AnimationController> _animControllers;
  late List<Animation<double>> _fadeAnimations;
  late List<Animation<Offset>> _slideAnimations;

  @override
  void initState() {
    super.initState();
    _initAnimations();
  }

  void _initAnimations() {
    _animControllers = List.generate(
      widget.choices.length,
      (index) => AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 400),
      ),
    );

    _fadeAnimations = _animControllers.map((ctrl) {
      return CurvedAnimation(parent: ctrl, curve: Curves.easeOut);
    }).toList();

    _slideAnimations = _animControllers.map((ctrl) {
      return Tween<Offset>(
        begin: const Offset(0, 0.3),
        end: Offset.zero,
      ).animate(CurvedAnimation(parent: ctrl, curve: Curves.easeOutCubic));
    }).toList();

    // Stagger the animations
    for (int i = 0; i < _animControllers.length; i++) {
      Future.delayed(Duration(milliseconds: 100 * i), () {
        if (mounted) _animControllers[i].forward();
      });
    }
  }

  @override
  void dispose() {
    for (final ctrl in _animControllers) {
      ctrl.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header label
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              widget.selectedKey != null ? '你的选择' : '请选择',
              style: GoogleFonts.inter(
                fontSize: 12,
                fontWeight: FontWeight.w500,
                color: theme.colorScheme.primary.withOpacity(0.8),
              ),
              textAlign: TextAlign.center,
            ),
          ),

          // Choice cards
          ...List.generate(widget.choices.length, (index) {
            final choice = widget.choices[index];
            final isSelected = widget.selectedKey == choice.key;
            final isOther =
                widget.selectedKey != null && widget.selectedKey != choice.key;

            return SlideTransition(
              position: _slideAnimations[index],
              child: FadeTransition(
                opacity: _fadeAnimations[index],
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _ChoiceCard(
                    choice: choice,
                    isSelected: isSelected,
                    isOther: isOther,
                    isDark: isDark,
                    disabled: widget.disabled || widget.selectedKey != null,
                    onTap: () => widget.onChoiceSelected(choice.key),
                  ),
                ),
              ),
            );
          }),
        ],
      ),
    );
  }
}

/// Individual choice card widget.
class _ChoiceCard extends StatelessWidget {
  final SceneChoice choice;
  final bool isSelected;
  final bool isOther;
  final bool isDark;
  final bool disabled;
  final VoidCallback onTap;

  const _ChoiceCard({
    required this.choice,
    required this.isSelected,
    required this.isOther,
    required this.isDark,
    required this.disabled,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final primaryColor = theme.colorScheme.primary;

    // Determine card styling based on state
    Color bgColor;
    Color borderColor;
    Color textColor;

    if (isSelected) {
      bgColor = primaryColor.withOpacity(isDark ? 0.2 : 0.1);
      borderColor = primaryColor;
      textColor = theme.colorScheme.onSurface;
    } else if (isOther) {
      bgColor = theme.colorScheme.onSurface.withOpacity(0.03);
      borderColor = theme.colorScheme.onSurface.withOpacity(0.1);
      textColor = theme.colorScheme.onSurface.withOpacity(0.4);
    } else {
      bgColor = isDark ? const Color(0xFF2A2A45) : Colors.white;
      borderColor = primaryColor.withOpacity(0.3);
      textColor = theme.colorScheme.onSurface;
    }

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: disabled ? null : onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            color: bgColor,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: borderColor, width: isSelected ? 1.5 : 1),
            boxShadow: isSelected
                ? [
                    BoxShadow(
                      color: primaryColor.withOpacity(0.15),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : null,
          ),
          child: Row(
            children: [
              // Choice indicator
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: 22,
                height: 22,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: isSelected
                      ? primaryColor
                      : Colors.transparent,
                  border: Border.all(
                    color: isSelected
                        ? primaryColor
                        : (isOther
                            ? theme.colorScheme.onSurface.withOpacity(0.2)
                            : primaryColor.withOpacity(0.4)),
                    width: 1.5,
                  ),
                ),
                child: isSelected
                    ? const Icon(Icons.check, size: 14, color: Colors.white)
                    : null,
              ),

              const SizedBox(width: 12),

              // Choice text
              Expanded(
                child: Text(
                  choice.text,
                  style: GoogleFonts.inter(
                    fontSize: 14,
                    fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                    color: textColor,
                    height: 1.4,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
