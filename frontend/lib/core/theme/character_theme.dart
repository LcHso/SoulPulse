import 'package:flutter/material.dart';

/// Character-specific color palette
///
/// Each AI character has a unique color identity that is applied
/// across the app for visual consistency and character recognition.
class CharacterColors {
  /// Primary brand color for the character
  final Color primary;

  /// Accent/highlight color (lighter shade of primary)
  final Color accent;

  /// Light gradient start color (for backgrounds)
  final Color gradient1;

  /// Dark gradient end color (for backgrounds)
  final Color gradient2;

  /// Vibrant accent for emphasis elements
  final Color vibrant;

  /// Text color on gradient backgrounds
  final Color textOnGradient;

  /// Dark mode gradient start color (subdued version for dark theme)
  final Color darkGradient1;

  /// Dark mode gradient end color (subdued version for dark theme)
  final Color darkGradient2;

  const CharacterColors({
    required this.primary,
    required this.accent,
    required this.gradient1,
    required this.gradient2,
    required this.vibrant,
    this.textOnGradient = Colors.white,
    Color? darkGradient1,
    Color? darkGradient2,
  })  : darkGradient1 = darkGradient1 ?? gradient1,
        darkGradient2 = darkGradient2 ?? gradient2;

  /// Get gradient1 color based on brightness
  Color getGradient1(Brightness brightness) =>
      brightness == Brightness.dark ? darkGradient1 : gradient1;

  /// Get gradient2 color based on brightness
  Color getGradient2(Brightness brightness) =>
      brightness == Brightness.dark ? darkGradient2 : gradient2;
}

/// Character theme registry with palette lookups
///
/// Provides consistent character-specific styling across the app.
/// Supports both Chinese and English character names with partial matching.
class CharacterTheme {
  /// Private palette registry
  static const Map<String, CharacterColors> _palettes = {
    // Starlin / 林星野 — warm idol, muted gold tones
    'starlin': CharacterColors(
      primary: Color(0xFFC4964A), // muted gold
      accent: Color(0xFFE0B87A),
      gradient1: Color(0xFFFFF8EE),
      gradient2: Color(0xFFC4964A),
      vibrant: Color(0xFFD4A65A),
      darkGradient1: Color(0xFF2E2517),
      darkGradient2: Color(0xFF4A3B22),
    ),

    // 季夜尘 / Ji Yechen — dark artistic, dusted plum
    '季夜尘': CharacterColors(
      primary: Color(0xFF6B4F8A), // dusted plum
      accent: Color(0xFF8B72A8),
      gradient1: Color(0xFFF0EBF5),
      gradient2: Color(0xFF6B4F8A),
      vibrant: Color(0xFF7D63A0),
      darkGradient1: Color(0xFF1E1530),
      darkGradient2: Color(0xFF2D2245),
    ),

    // 陆骁 / Lu Xiao — athletic, burnt sienna
    '陆骁': CharacterColors(
      primary: Color(0xFFB85A3A), // burnt sienna
      accent: Color(0xFFD47C5E),
      gradient1: Color(0xFFFBF0EA),
      gradient2: Color(0xFFB85A3A),
      vibrant: Color(0xFFC86A4A),
      darkGradient1: Color(0xFF2B1810),
      darkGradient2: Color(0xFF3D251A),
    ),

    // 陆晨曦 / Lu Chenxi — warm sand
    '陆晨曦': CharacterColors(
      primary: Color(0xFFB89A7A), // warm sand
      accent: Color(0xFFD4B89A),
      gradient1: Color(0xFFFAF4EC),
      gradient2: Color(0xFFB89A7A),
      vibrant: Color(0xFFC0A080),
      darkGradient1: Color(0xFF231D15),
      darkGradient2: Color(0xFF362E22),
    ),

    // 顾言深 / Gu Yanshen — cool professional, steel blue
    '顾言深': CharacterColors(
      primary: Color(0xFF3D5A73), // steel blue
      accent: Color(0xFF5A7A93),
      gradient1: Color(0xFFEEF3F7),
      gradient2: Color(0xFF3D5A73),
      vibrant: Color(0xFF4A6A83),
      darkGradient1: Color(0xFF131D26),
      darkGradient2: Color(0xFF1E2D3A),
    ),

    // 林屿 / Lin Yu — sporty sage green
    '林屿': CharacterColors(
      primary: Color(0xFF4A8A5E), // sage green
      accent: Color(0xFF6AAA7E),
      gradient1: Color(0xFFEDF7F0),
      gradient2: Color(0xFF4A8A5E),
      vibrant: Color(0xFF5A9A6E),
      darkGradient1: Color(0xFF142018),
      darkGradient2: Color(0xFF1E3025),
    ),

    // 沈默白 / Shen Mobai — elegant slate
    '沈默白': CharacterColors(
      primary: Color(0xFF5A6872), // slate
      accent: Color(0xFF7A8892),
      gradient1: Color(0xFFEFF2F4),
      gradient2: Color(0xFF5A6872),
      vibrant: Color(0xFF6A7882),
      darkGradient1: Color(0xFF171C20),
      darkGradient2: Color(0xFF232A30),
    ),
  };

  /// English name aliases mapping to palette keys
  static const Map<String, String> _englishAliases = {
    'ji yechen': '季夜尘',
    'yechen': '季夜尘',
    'lu xiao': '陆骁',
    'xiao': '陆骁',
    'lu chenxi': '陆晨曦',
    'chenxi': '陆晨曦',
    'gu yanshen': '顾言深',
    'yanshen': '顾言深',
    'lin yu': '林屿',
    'yu': '林屿',
    'shen mobai': '沈默白',
    'mobai': '沈默白',
    'lin xingye': 'starlin',
    'xingye': 'starlin',
  };

  /// Default fallback palette (rose-gold to match global theme)
  static const CharacterColors _default = CharacterColors(
    primary: Color(0xFFB76E79),
    accent: Color(0xFF9C8AA5),
    gradient1: Color(0xFFFAFAF8),
    gradient2: Color(0xFFB76E79),
    vibrant: Color(0xFFC9848D),
    darkGradient1: Color(0xFF1A1A2E),
    darkGradient2: Color(0xFF2A2A45),
  );

  /// Get character color palette by AI name
  ///
  /// Performs case-insensitive partial matching to support
  /// both Chinese and English names.
  ///
  /// [aiName] The AI character name (can be Chinese or English)
  static CharacterColors getPalette(String? aiName) {
    if (aiName == null || aiName.isEmpty) return _default;

    final lower = aiName.toLowerCase().trim();

    // Check for direct key match first
    for (final entry in _palettes.entries) {
      if (lower == entry.key.toLowerCase()) {
        return entry.value;
      }
    }

    // Check English aliases
    if (_englishAliases.containsKey(lower)) {
      final key = _englishAliases[lower]!;
      return _palettes[key] ?? _default;
    }

    // Partial match (handles cases like "林星野的" or "Starlin AI")
    for (final entry in _palettes.entries) {
      if (lower.contains(entry.key.toLowerCase()) ||
          entry.key.toLowerCase().contains(lower)) {
        return entry.value;
      }
    }

    // Check partial alias match
    for (final entry in _englishAliases.entries) {
      if (lower.contains(entry.key) || entry.key.contains(lower)) {
        final paletteKey = entry.value;
        return _palettes[paletteKey] ?? _default;
      }
    }

    return _default;
  }

  /// Create a gradient from character colors
  ///
  /// [colors] The character color palette
  /// [begin] Gradient start alignment (default: topLeft)
  /// [end] Gradient end alignment (default: bottomRight)
  /// [brightness] Current theme brightness (defaults to light)
  static LinearGradient createGradient(
    CharacterColors colors, {
    Alignment begin = Alignment.topLeft,
    Alignment end = Alignment.bottomRight,
    Brightness brightness = Brightness.light,
  }) {
    return LinearGradient(
      colors: [
        colors.getGradient1(brightness),
        colors.primary,
        colors.vibrant,
      ],
      begin: begin,
      end: end,
    );
  }

  /// Create a subtle story ring gradient
  ///
  /// Uses gradient1, primary, and vibrant for a character-specific
  /// Instagram-style story ring effect.
  /// [brightness] Current theme brightness (defaults to light)
  static LinearGradient createStoryGradient(
    CharacterColors colors, {
    Brightness brightness = Brightness.light,
  }) {
    return LinearGradient(
      colors: [
        colors.getGradient1(brightness),
        colors.primary,
        colors.vibrant,
      ],
      begin: Alignment.topRight,
      end: Alignment.bottomLeft,
    );
  }
}
